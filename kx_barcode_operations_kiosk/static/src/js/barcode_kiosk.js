/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { BarcodeHandler } from "./barcode_handler";

/**
 * BarcodeKioskInterface
 * - Operation types: incoming, outgoing, internal, incoming_return, outgoing_return, scrap
 * - Prioritized scan recognition is done on the backend (picking/location/product/lot/serial)
 * - Frontend expects backend to return { success, type, data, message, scan_line_id }
 */
export class BarcodeKioskInterface extends Component {

    static props = {
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
        updateActionState: { type: Function, optional: true },
        className: { type: String, optional: true },
    };

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.action = useService("action");
        this.barcodeInputRef = useRef("barcodeInput");

        const savedSessionState = sessionStorage.getItem('barcode_session_state');
        const savedScans = sessionStorage.getItem('barcode_scans');

        const restoredState = savedSessionState ? JSON.parse(savedSessionState) : {};
        const loadedScans = savedScans ? JSON.parse(savedScans) : [];

        this.state = useState({
            userName: "",
            uid: 0,
            avatar: "",
            role: "",
            isInternal: false,

            sessionId: restoredState.sessionId || null,
            sessionName: restoredState.sessionName || '',
            operationType: restoredState.operationType || '', // 'incoming'|'outgoing'|'internal'|'incoming_return'|'outgoing_return'|'scrap'
            pickingId: restoredState.pickingId || null,
            pickingName: restoredState.pickingName || '',
            scannedItems: loadedScans,
            allPickings: [],
            totalScans: restoredState.totalScans || 0,
            successfulScans: restoredState.successfulScans || 0,
            failedScans: restoredState.failedScans || 0,
            isLoading: false,
            showOperationSelector: !restoredState.sessionId,
            currentBarcode: '',
            lastScanType: restoredState.lastScanType || null,
            currentPicking: restoredState.currentPicking || null,
        });

        onWillStart(async () => {
            await this.loadSettings();
            await this.loadSession();
            await this.loadAllPickings();


            const info = await rpc("/web/session/get_session_info", {});
            this.state.userName = info.name;
            this.state.uid = info.uid;

            const userData = await rpc("/web/dataset/call_kw/res.users/read", {
                model: "res.users",
                method: "read",
                args: [[info.uid], ["image_128", "groups_id"]],
                kwargs: {},
            });

            if (userData && userData[0].image_128) {
                this.state.avatar = "data:image/png;base64," + userData[0].image_128;
            }

            const groups = userData[0].groups_id || [];
            this.state.isInternal = groups.length > 0;

            const groupData = groups.length ? await rpc("/web/dataset/call_kw/res.groups/read", {
                model: "res.groups",
                method: "read",
                args: [groups, ["name", "category_id"]],
                kwargs: {},
            }) : [];

            const internalGroup = (groupData || []).find(g => g.category_id && g.category_id[1] !== "Portal" && g.category_id[1] !== "Public");
            this.state.role = internalGroup ? internalGroup.name : "User";

            if (this.state.sessionId) {
                // ensure operationType persisted and pickings loaded appropriate to it
                await this.loadAllPickings();
            }
        });

        onMounted(() => {
            this.focusBarcodeInput();
        });
    }

    saveSessionState() {
        const sessionState = {
            sessionId: this.state.sessionId,
            sessionName: this.state.sessionName,
            operationType: this.state.operationType,
            pickingId: this.state.pickingId,
            pickingName: this.state.pickingName,
            currentPicking: this.state.currentPicking,
            lastScanType: this.state.lastScanType,
            totalScans: this.state.totalScans,
            successfulScans: this.state.successfulScans,
            failedScans: this.state.failedScans,
        };
        sessionStorage.setItem('barcode_session_state', JSON.stringify(sessionState));
    }

    clearSessionState() {
        sessionStorage.removeItem('barcode_session_state');
        sessionStorage.removeItem('barcode_scans');
    }

    async loadSession() {
        this.sessionData = await rpc("/barcode_kiosk/get_session_data", {
            session_id: this.props.session_id,
        });
    }

    async loadSettings() {
        const params = await this.orm.call(
            'ir.config_parameter',
            'get_param',
            ['kx_barcode_operations_kiosk.enable_sound']
        );
        this.enableSound = params === 'True';
    }

    focusBarcodeInput() {
        if (this.barcodeInputRef.el) {
            this.barcodeInputRef.el.focus();
        }
    }

    // Operation starter: operationType must be one of accepted values
    async startSession(operationType) {
        this.state.isLoading = true;
        try {
            // normalize few aliases (if UI uses 'return' or 'scrap' previously)
            if (operationType === 'return') {
                operationType = 'incoming_return';
            }
            if (operationType === 'scrap') {
                operationType = 'scrap';
            }

            const result = await rpc('/barcode_kiosk/create_session', {
                operation_type: operationType,
            });

            if (result.error) {
                this.notification.add(result.error, { type: 'danger' });
                return;
            }

            this.state.sessionId = result.session_id;
            this.state.sessionName = result.session_name;
            this.state.operationType = operationType;
            this.state.showOperationSelector = false;

            this.saveSessionState();

            this.notification.add(`Session ${result.session_name} started`, {
                type: 'success'
            });

            // load pickings constrained to operation type (internal -> internal only)
            await this.loadAllPickings();
            this.focusBarcodeInput();

        } catch (error) {
            console.error('Error starting session:', error);
            this.notification.add('Error starting session', { type: 'danger' });
        } finally {
            this.state.isLoading = false;
        }
    }

    async onBarcodeInput(ev) {
        if (ev.key === 'Enter' && this.state.currentBarcode) {
            await this.processBarcode(this.state.currentBarcode);
            this.state.currentBarcode = '';
        }
    }

    /**
     * processBarcode - Enhanced with operation type validation
     */
    async processBarcode(barcode) {
        if (!this.state.sessionId) {
            this.notification.add('Please start a session first', { type: 'warning' });
            return;
        }

        if (!barcode || !barcode.trim()) {
            return;
        }

        this.state.isLoading = true;

        try {
            const result = await rpc('/barcode_kiosk/process_scan', {
                session_id: this.state.sessionId,
                barcode: barcode.trim(),
                operation_type: this.state.operationType,
            });

            console.log('Scan result:', result);

            if (result.success) {
                this.state.lastScanType = result.type;
                const scannedItem = {
                    barcode: barcode,
                    status: 'success',
                    time: new Date().toLocaleTimeString(),
                    type: result.type,
                    message: result.message,
                    scan_line_id: result.scan_line_id || null,
                };

                // Enrich UI item depending on returned type
                if (result.type === 'product') {
                    scannedItem.product_name = result.data.name;
                    scannedItem.product_id = result.data.id;
                    scannedItem.quantity = result.data.qty_done || 1;
                    scannedItem.expected = result.data.expected || 0;
                    scannedItem.lot = result.data.lot_name || null;
                } else if (result.type === 'picking') {
                    scannedItem.product_name = `Picking: ${result.data.name}`;
                    scannedItem.picking_id = result.data.id;
                    scannedItem.picking_name = result.data.name;
                    scannedItem.partner = result.data.partner;
                    scannedItem.state = result.data.state;
                    // Set as current picking for session
                    this.state.currentPicking = result.data;
                    this.state.pickingId = result.data.id;
                    this.state.pickingName = result.data.name;
                } else if (result.type === 'location') {
                    scannedItem.product_name = `Location: ${result.data.name}`;
                    scannedItem.location_id = result.data.id;
                } else if (result.type === 'lot' || result.type === 'serial') {
                    scannedItem.product_name = result.data.product_name || 'Lot/Serial';
                    scannedItem.lot = result.data.lot_name || result.data.serial;
                    scannedItem.product_id = result.data.product_id || null;
                }

                // Add to UI list
                this.state.scannedItems.unshift(scannedItem);
                sessionStorage.setItem('barcode_scans', JSON.stringify(this.state.scannedItems));

                if (this.enableSound) {
                    this.playSuccessSound();
                }

                // Show success notification with icon based on type
                const typeIcons = {
                    'picking': 'fa-cube',
                    'product': 'fa-barcode',
                    'location': 'fa-map-marker',
                    'lot': 'fa-tag',
                    'serial': 'fa-qrcode',
                };
                
                const icon = typeIcons[result.type] || 'fa-check';

                this.notification.add(result.message || "Scan recorded", {
                    type: 'success',
                    title: `<i class="fa ${icon}"></i> ${result.type ? result.type.toUpperCase() : 'SCAN'} Scanned`
                });

                this.state.successfulScans++;
                this.state.totalScans++;
                this.saveSessionState();

            } else {
                // FAILED SCAN - Show detailed error
                const failedItem = {
                    barcode: barcode,
                    status: 'error',
                    time: new Date().toLocaleTimeString(),
                    product_name: result.data?.picking_name || 'Error',
                    message: result.message || 'Unknown barcode',
                    type: result.type || 'unknown',
                };

                // Add additional info for operation type mismatch
                if (result.data) {
                    failedItem.error_details = {
                        scanned_type: result.data.scanned_type,
                        session_type: result.data.session_type,
                    };
                }

                this.state.scannedItems.unshift(failedItem);
                sessionStorage.setItem('barcode_scans', JSON.stringify(this.state.scannedItems));

                if (this.enableSound) {
                    this.playErrorSound();
                }

                // Show error notification with detailed message
                // Check if it's an operation type mismatch
                if (result.message && result.message.includes('Operation Type Mismatch')) {
                    // Show prominent error for wrong operation type
                    this.notification.add(result.message, {
                        type: 'danger',
                        title: '⚠️ Wrong Operation Type',
                        sticky: true,  // Keep notification visible
                    });
                } else {
                    // Regular error
                    this.notification.add(result.message || "Invalid scan", {
                        type: 'danger',
                        title: '❌ Scan Failed'
                    });
                }

                this.state.failedScans++;
                this.state.totalScans++;
                this.saveSessionState();
            }

            // After every scan refresh pickings and session counters
            await this.loadAllPickings();
            await this.refreshSessionData();

        } catch (error) {
            console.error('Error processing barcode:', error);
            
            const errorMessage = error.message || 'Error processing barcode';
            
            this.notification.add(errorMessage, {
                type: 'danger',
                title: '❌ System Error'
            });

            if (this.enableSound) {
                this.playErrorSound();
            }

            this.state.scannedItems.unshift({
                barcode: barcode,
                status: 'error',
                time: new Date().toLocaleTimeString(),
                product_name: 'System Error',
                message: errorMessage,
            });

            this.state.failedScans++;
            this.state.totalScans++;
            this.saveSessionState();

        } finally {
            this.state.isLoading = false;
            this.focusBarcodeInput();
        }
    }

    async refreshSessionData() {
        if (!this.state.sessionId) return;

        try {
            const data = await rpc('/barcode_kiosk/get_session_data', {
                session_id: this.state.sessionId
            });

            if (!data.error) {
                this.state.pickingId = data.picking_id;
                this.state.pickingName = data.picking_name;
                this.state.totalScans = data.total_scans || this.state.totalScans;
                this.state.successfulScans = data.successful_scans || this.state.successfulScans;
                this.state.failedScans = data.failed_scans || this.state.failedScans;
                this.saveSessionState();
            }
        } catch (error) {
            console.error('Error refreshing session data:', error);
        }
    }

    /**
     * loadAllPickings - Fixed version
     * - Builds a domain filtered by session operationType
     * - For internal sessions -> only internal pickings are loaded
     * - For scrap -> show scrap records or relevant pickings
     */
    async loadAllPickings() {
        // 🔐 SAFETY CHECK – Prevent crash when no session is active
        if (!this.state.operationType) {
            console.warn("No operation type set. Skipping loadAllPickings.");
            this.state.allPickings = [];
            return;
        }

        try {
            // Map operation types to picking types
            const PICKING_TYPE_MAP = {
                "incoming": ["incoming", "receipt"],
                "outgoing": ["outgoing", "delivery"],
                "internal": ["internal"],
                "scrap": ["scrap"],
                "incoming_return": ["incoming", "receipt"],
                "outgoing_return": ["outgoing", "delivery"],
            };

            const pickingTypes = PICKING_TYPE_MAP[this.state.operationType] || [];
            
            console.log('Loading pickings for operation type:', this.state.operationType);
            console.log('Filtering by picking types:', pickingTypes);

            const result = await rpc("/barcode_kiosk/get_pickings", {
                session_id: this.state.sessionId,
                operation_type: this.state.operationType,
                picking_types: pickingTypes,
                show_returns: this.state.operationType === "incoming_return" || this.state.operationType === "outgoing_return",
            });

            if (result.error) {
                console.error('Error loading pickings:', result.error);
                this.state.allPickings = [];
                return;
            }

            this.state.allPickings = result.pickings || result || [];
            console.log('Loaded pickings:', this.state.allPickings.length);

        } catch (error) {
            console.error('Error in loadAllPickings:', error);
            this.state.allPickings = [];
            this.notification.add('Error loading pickings', { type: 'danger' });
        }
    }

    async updateQuantity(picking_id, product_id, new_qty) {
        try {
            const picking = this.state.allPickings.find(p => p.id === picking_id);
            if (picking) {
                const move = picking.move_lines.find(m => m.product_id === product_id);
                if (move) {
                    move.qty_done = parseFloat(new_qty) || 0;
                }
            }

            const result = await rpc('/barcode_kiosk/update_move_quantity', {
                picking_id: picking_id,
                product_id: product_id,
                quantity: parseFloat(new_qty) || 0
            });

            if (result.success) {
                this.notification.add('Quantity updated', { type: 'success' });
            } else {
                this.notification.add(result.error || 'Failed to update', { type: 'danger' });
                await this.loadAllPickings();
            }

        } catch (error) {
            console.error('Error updating quantity:', error);
            this.notification.add('Error updating quantity', { type: 'danger' });
            await this.loadAllPickings();
        }
    }

    async validateSinglePicking(picking_id) {
        if (!confirm('Validate this picking? This action cannot be undone.')) {
            return;
        }

        this.state.isLoading = true;
        try {
            const result = await rpc('/barcode_kiosk/validate_picking', {
                picking_id: picking_id
            });

            if (result.success) {
                this.notification.add('Picking validated successfully!', { type: 'success' });
                await this.loadAllPickings();
                await this.refreshSessionData();
            } else {
                this.notification.add(result.error || 'Validation failed', { type: 'danger' });
            }
        } catch (error) {
            console.error('Error validating picking:', error);
            this.notification.add('Error validating picking', { type: 'danger' });
        } finally {
            this.state.isLoading = false;
        }
    }

    async validateOperation() {
        if (!this.state.sessionId) return;

        this.state.isLoading = true;

        try {
            const result = await rpc('/barcode_kiosk/validate_operation', {
                session_id: this.state.sessionId
            });

            if (result.success) {
                this.notification.add('Operation validated successfully!', {
                    type: 'success'
                });
                await this.closeSession();
            } else {
                this.notification.add(result.error || 'Error validating operation', {
                    type: 'danger'
                });
            }
        } catch (error) {
            console.error('Error validating operation:', error);
            this.notification.add('Error validating operation', { type: 'danger' });
        } finally {
            this.state.isLoading = false;
        }
    }

    async closeSession() {
        if (!this.state.sessionId) return;

        try {
            await rpc('/barcode_kiosk/close_session', {
                session_id: this.state.sessionId
            });

            this.clearSessionState();

            this.state.sessionId = null;
            this.state.sessionName = '';
            this.state.operationType = '';
            this.state.pickingId = null;
            this.state.pickingName = '';
            this.state.scannedItems = [];
            this.state.allPickings = [];
            this.state.totalScans = 0;
            this.state.successfulScans = 0;
            this.state.failedScans = 0;
            this.state.showOperationSelector = true;
            this.state.lastScanType = null;
            this.state.currentPicking = null;

            this.notification.add('Session closed', { type: 'info' });

        } catch (error) {
            console.error('Error closing session:', error);
            this.notification.add('Error closing session', { type: 'danger' });
        }
    }

    playSuccessSound() {
        try {
            const context = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = context.createOscillator();
            const gainNode = context.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(context.destination);

            oscillator.frequency.value = 1000;
            oscillator.type = 'sine';
            gainNode.gain.value = 0.25;

            oscillator.start(context.currentTime);
            oscillator.stop(context.currentTime + 0.08);
        } catch (e) {
            // audio may be blocked in some browsers
            console.warn('Sound failed', e);
        }
    }

    // Enhanced error sound for operation type mismatch
    playErrorSound() {
        try {
            const context = new (window.AudioContext || window.webkitAudioContext)();
            
            // Play two beeps for error
            for (let i = 0; i < 2; i++) {
                const oscillator = context.createOscillator();
                const gainNode = context.createGain();

                oscillator.connect(gainNode);
                gainNode.connect(context.destination);

                oscillator.frequency.value = 220;
                oscillator.type = 'sine';
                gainNode.gain.value = 0.25;

                const startTime = context.currentTime + (i * 0.15);
                oscillator.start(startTime);
                oscillator.stop(startTime + 0.08);
            }
        } catch (e) {
            console.warn('Sound failed', e);
        }
    }

    getOperationTypeLabel(type) {
        const labels = {
            'incoming': 'Incoming (Receipts)',
            'outgoing': 'Outgoing (Deliveries)',
            'internal': 'Internal Transfers',
            'incoming_return': 'Incoming - Returns',
            'outgoing_return': 'Outgoing - Returns',
            'scrap': 'Scrap Operations',
        };
        return labels[type] || type;
    }

    getPickingBadgeClass(state) {
        const classes = {
            'draft': 'badge-secondary',
            'waiting': 'badge-warning',
            'confirmed': 'badge-info',
            'assigned': 'badge-primary',
            'done': 'badge-success',
            'cancel': 'badge-danger',
        };
        return classes[state] || 'badge-secondary';
    }

    async openScanRecords() {
        if (!this.state.sessionId) {
            this.notification.add('No active session', { type: 'warning' });
            return;
        }

        try {
            await this.action.doAction({
                name: 'Scan Records',
                type: 'ir.actions.act_window',
                res_model: 'barcode.kiosk.scan.line',
                views: [[false, 'list'], [false, 'form']],
                view_mode: 'list,form',
                domain: [['session_id', '=', this.state.sessionId]],
                context: {
                    default_session_id: this.state.sessionId,
                },
                target: 'current',
            });
        } catch (error) {
            console.error('Error opening scan records:', error);
            this.notification.add('Error opening scan records', { type: 'danger' });
        }
    }

    async openScanDetail(item) {
        if (!item.scan_line_id) {
            this.notification.add('Scan record ID not found', { type: 'warning' });
            return;
        }

        try {
            await this.action.doAction({
                name: 'Scan Detail',
                type: 'ir.actions.act_window',
                res_model: 'barcode.kiosk.scan.line',
                res_id: item.scan_line_id,
                views: [[false, 'form']],
                view_mode: 'form',
                target: 'new',
            });
        } catch (error) {
            console.error('Error opening scan detail:', error);
            this.notification.add('Error opening scan detail', { type: 'danger' });
        }
    }

    async openPickingDetail(picking) {
        if (!picking.id) {
            this.notification.add('Picking ID not found', { type: 'warning' });
            return;
        }

        try {
            await this.action.doAction({
                name: 'Picking Detail',
                type: 'ir.actions.act_window',
                res_model: 'stock.picking',
                res_id: picking.id,
                views: [[false, 'form']],
                view_mode: 'form',
                target: 'new',
            });
        } catch (error) {
            console.error('Error opening picking detail:', error);
            this.notification.add('Error opening picking detail', { type: 'danger' });
        }
    }

    // Add these methods to your BarcodeKioskInterface class

    /**
     * Get operation type badge CSS class
     */
    getOperationTypeBadgeClass(type) {
        const classes = {
            'incoming': 'badge-primary',
            'outgoing': 'badge-warning',
            'internal': 'badge-info',
            'incoming_return': 'badge-secondary',
            'outgoing_return': 'badge-secondary',
            'scrap': 'badge-danger',
        };
        return classes[type] || 'badge-secondary';
    }

    /**
     * Get operation type icon
     */
    getOperationTypeIcon(type) {
        const icons = {
            'incoming': 'fa-arrow-down',
            'outgoing': 'fa-arrow-up',
            'internal': 'fa-exchange',
            'incoming_return': 'fa-undo',
            'outgoing_return': 'fa-reply',
            'scrap': 'fa-trash',
        };
        return icons[type] || 'fa-cube';
    }

    /**
     * Get expected picking format for current operation
     */
    getExpectedPickingFormat(operationType) {
        const formats = {
            'incoming': 'WH/IN/*',
            'outgoing': 'WH/OUT/*',
            'internal': 'WH/INT/*',
            'incoming_return': 'WH/IN/* (Returns)',
            'outgoing_return': 'WH/OUT/* (Returns)',
            'scrap': 'WH/INT/* (Scrap)',
        };
        return formats[operationType] || 'Unknown';
    }

    /**
     * Validate if barcode matches expected operation type
     * (Client-side pre-validation before sending to server)
     */
    validateBarcodeFormat(barcode, operationType) {
        // Common picking patterns
        const patterns = {
            'incoming': /^WH\/IN\//i,
            'outgoing': /^WH\/OUT\//i,
            'internal': /^WH\/INT\//i,
        };
        
        const pattern = patterns[operationType];
        if (!pattern) return true; // Unknown type, let server validate
        
        // If it looks like a picking barcode but doesn't match pattern
        if (barcode.match(/^WH\//i) && !barcode.match(pattern)) {
            return false;
        }
        
        return true; // Either matches or not a picking barcode
    }
    async openBackendSessions() {
        try {
            await this.action.doAction("kx_barcode_operations_kiosk.action_barcode_kiosk_session");
        } catch (error) {
            console.error("Error opening Kiosk Sessions:", error);
            this.notification.add("Cannot open session list", { type: "danger" });
        }
    }

    /**
     * Enhanced processBarcode with client-side pre-validation
     */
    async processBarcode(barcode) {
        if (!this.state.sessionId) {
            this.notification.add('Please start a session first', { type: 'warning' });
            return;
        }

        if (!barcode || !barcode.trim()) {
            return;
        }

        // CLIENT-SIDE PRE-VALIDATION for picking barcodes
        if (!this.validateBarcodeFormat(barcode.trim(), this.state.operationType)) {
            const expected = this.getExpectedPickingFormat(this.state.operationType);
            
            this.notification.add(
                `⚠️ Wrong picking format!\n\nYou scanned: ${barcode}\nExpected: ${expected}\n\nCurrent session: ${this.getOperationTypeLabel(this.state.operationType)}`,
                {
                    type: 'warning',
                    title: 'Invalid Picking Format',
                    sticky: true,
                }
            );
            
            if (this.enableSound) {
                this.playErrorSound();
            }
            
            // Add to failed scans
            this.state.scannedItems.unshift({
                barcode: barcode,
                status: 'error',
                time: new Date().toLocaleTimeString(),
                product_name: 'Format Error',
                message: `Wrong format. Expected ${expected}`,
            });
            
            this.state.failedScans++;
            this.state.totalScans++;
            this.saveSessionState();
            
            this.focusBarcodeInput();
            return;
        }

        // Continue with server-side processing...
        this.state.isLoading = true;

        try {
            const result = await rpc('/barcode_kiosk/process_scan', {
                session_id: this.state.sessionId,
                barcode: barcode.trim(),
                operation_type: this.state.operationType,
            });

            console.log('Scan result:', result);

            if (result.success) {
                this.state.lastScanType = result.type;
                const scannedItem = {
                    barcode: barcode,
                    status: 'success',
                    time: new Date().toLocaleTimeString(),
                    type: result.type,
                    message: result.message,
                    scan_line_id: result.scan_line_id || null,
                };

                // enrich UI item depending on returned type
                if (result.type === 'product') {
                    scannedItem.product_name = result.data.name;
                    scannedItem.product_id = result.data.id;
                    scannedItem.quantity = result.data.qty_done || 1;
                    scannedItem.expected = result.data.expected || 0;
                    scannedItem.lot = result.data.lot_name || null;
                } else if (result.type === 'picking') {
                    scannedItem.product_name = `Picking: ${result.data.name}`;
                    scannedItem.picking_id = result.data.id;
                    scannedItem.picking_name = result.data.name;
                    scannedItem.partner = result.data.partner;
                    scannedItem.state = result.data.state;
                    // set as current picking for session
                    this.state.currentPicking = result.data;
                    this.state.pickingId = result.data.id;
                    this.state.pickingName = result.data.name;
                } else if (result.type === 'location') {
                    scannedItem.product_name = `Location: ${result.data.name}`;
                    scannedItem.location_id = result.data.id;
                } else if (result.type === 'lot' || result.type === 'serial') {
                    scannedItem.product_name = result.data.product_name || 'Lot/Serial';
                    scannedItem.lot = result.data.lot_name || result.data.serial;
                    scannedItem.product_id = result.data.product_id || null;
                } else if (result.type === 'scrap') {
                    scannedItem.product_name = result.data.name || 'Scrap';
                    scannedItem.scrap_qty = result.data.scrap_qty || 1;
                } else if (result.type === 'return') {
                    scannedItem.product_name = result.data.name || 'Return';
                }

                // add to UI list
                this.state.scannedItems.unshift(scannedItem);
                sessionStorage.setItem('barcode_scans', JSON.stringify(this.state.scannedItems));

                if (this.enableSound) {
                    this.playSuccessSound();
                }

                this.notification.add(result.message || "Scan recorded", {
                    type: 'success',
                    title: `${result.type ? result.type.toUpperCase() : 'SCAN'} Scanned`
                });

                this.state.successfulScans++;
                this.state.totalScans++;
                this.saveSessionState();

            } else {
                const failedItem = {
                    barcode: barcode,
                    status: 'error',
                    time: new Date().toLocaleTimeString(),
                    product_name: 'Unknown',
                    message: result.message || 'Unknown barcode',
                };

                this.state.scannedItems.unshift(failedItem);
                sessionStorage.setItem('barcode_scans', JSON.stringify(this.state.scannedItems));

                if (this.enableSound) {
                    this.playErrorSound();
                }

                this.notification.add(result.message || "Invalid scan", { type: 'danger' });

                this.state.failedScans++;
                this.state.totalScans++;
                this.saveSessionState();
            }

            // After every scan refresh pickings and session counters
            await this.loadAllPickings();
            await this.refreshSessionData();
            
        } catch (error) {
            // ... error handling ...
        } finally {
            this.state.isLoading = false;
            this.focusBarcodeInput();
        }
    }
}


BarcodeKioskInterface.template = "kx_barcode_operations_kiosk.KioskInterface";
BarcodeKioskInterface.components = { BarcodeHandler };

registry.category("actions").add("barcode_kiosk_interface", BarcodeKioskInterface);
