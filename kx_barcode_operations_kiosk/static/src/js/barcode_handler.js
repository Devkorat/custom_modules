/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";

export class BarcodeHandler extends Component {

    static props = {
        onBarcodeScanned: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({
            buffer: '',
            lastKeyTime: 0,
            allPickings: [],
        });
        
        this.keyPressThreshold = 50; // milliseconds between keypresses for barcode scanner
        
        onMounted(() => {
            this.addBarcodeListener();
        });

        onWillUnmount(() => {
            this.removeBarcodeListener();
        });
    }

    addBarcodeListener() {
        this.onKeyPress = this._onKeyPress.bind(this);
        document.addEventListener('keypress', this.onKeyPress);
    }
    
    removeBarcodeListener() {
        if (this.onKeyPress) {
            document.removeEventListener('keypress', this.onKeyPress);
        }
    }
    
    _onKeyPress(event) {
        const currentTime = new Date().getTime();
        
        // Check if this is likely from a barcode scanner (rapid keypresses)
        if (currentTime - this.state.lastKeyTime > 100) {
            this.state.buffer = '';
        }
        
        this.state.lastKeyTime = currentTime;
        
        // Enter key - process the barcode
        if (event.keyCode === 13 || event.key === 'Enter') {
            if (this.state.buffer.length > 0) {
                this.processBarcodeFromScanner(this.state.buffer);
                this.state.buffer = '';
            }
            event.preventDefault();
            return;
        }
        
        // Add character to buffer
        if (event.key && event.key.length === 1) {
            this.state.buffer += event.key;
        }
    }
    
    processBarcodeFromScanner(barcode) {
        // This method should be overridden by components using this handler
        console.log('Barcode scanned:', barcode);
        if (this.props.onBarcodeScanned) {
            this.props.onBarcodeScanned(barcode);
        }
    }
    
    playSuccessSound() {
        // Play success beep
        const audio = new Audio('/kx_barcode_operations_kiosk/static/src/sounds/success.mp3');
        audio.play().catch(() => {
            // Fallback to system beep
            const context = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = context.createOscillator();
            const gainNode = context.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(context.destination);
            
            oscillator.frequency.value = 800;
            oscillator.type = 'sine';
            gainNode.gain.value = 0.3;
            
            oscillator.start(context.currentTime);
            oscillator.stop(context.currentTime + 0.1);
        });
    }
    
    playErrorSound() {
        // Play error beep
        const audio = new Audio('/kx_barcode_operations_kiosk/static/src/sounds/error.mp3');
        audio.play().catch(() => {
            // Fallback to system beep
            const context = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = context.createOscillator();
            const gainNode = context.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(context.destination);
            
            oscillator.frequency.value = 200;
            oscillator.type = 'sine';
            gainNode.gain.value = 0.3;
            
            oscillator.start(context.currentTime);
            oscillator.stop(context.currentTime + 0.3);
        });
    }
}

BarcodeHandler.template = 'kx_barcode_operations_kiosk.BarcodeHandler';