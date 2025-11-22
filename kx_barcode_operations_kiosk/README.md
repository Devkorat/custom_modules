# Barcode Operations Kiosk for Odoo 18

## Overview

The **Barcode Operations Kiosk** module provides a modern, touch-friendly kiosk interface for warehouse operations. It enables warehouse staff to perform inventory movements through barcode scanning, streamlining processes like receipts, deliveries, internal transfers, returns, and scrap operations.

## Features

### Core Functionality
- **Kiosk-Style Interface**: Large buttons, touch-friendly design
- **Multiple Operation Types**:
  - Incoming Shipments (Receipts)
  - Outgoing Shipments (Deliveries)
  - Internal Transfers
  - Return Orders
  - Scrap Operations

### Scanning Capabilities
- Real-time barcode/QR code scanning
- Support for standard GS1 and custom barcode formats
- Automatic product, location, and operation detection
- Batch and lot number tracking
- Audio and visual feedback

### Session Management
- User authentication via barcode
- Session tracking and history
- Real-time statistics
- Detailed scan logs

### Mobile & Tablet Support
- Responsive design
- Fullscreen kiosk mode
- Works with barcode scanners and manual input
- Optimized for touchscreen devices

## Installation

1. Download the module
2. Extract to your Odoo addons directory
3. Update Apps List (Developer mode)
4. Search for "Barcode Operations Kiosk"
5. Click Install

## Configuration

After installation:

1. Go to **Settings → Inventory → Barcode Kiosk Settings**
2. Configure:
   - Enable/disable sound alerts
   - Set auto-validation preferences
   - Configure session timeout
   - Adjust scanning behavior

## Usage

### Starting a Session

1. Navigate to **Barcode Kiosk → Kiosk Interface**
2. Select your operation type:
   - Incoming (for receiving goods)
   - Outgoing (for shipping)
   - Internal (for transfers)
   - Return (for RMAs)
   - Scrap (for waste)

### Scanning Products

1. Click in the barcode input field (or let scanner focus automatically)
2. Scan product barcodes
3. View real-time feedback (green = success, red = error)
4. Monitor progress in the statistics section

### Completing Operations

1. Scan all required items
2. Click "Validate" to complete the operation
3. System automatically updates inventory
4. Close session when done

## User Permissions

### Barcode Kiosk User
- Can start sessions
- Can scan and process items
- Can view own sessions
- Cannot delete sessions

### Barcode Kiosk Manager
- All User permissions
- Can view all sessions
- Can modify/delete sessions
- Can configure settings

## Technical Details

### Dependencies
- base
- stock
- product
- mail
- web

### Models
- `barcode.kiosk.session` - Session tracking
- `barcode.kiosk.scan.line` - Individual scans
- Extensions to `stock.picking` and `stock.move`

### API Endpoints
- `/barcode_kiosk/process_scan` - Process barcode
- `/barcode_kiosk/create_session` - Start session
- `/barcode_kiosk/close_session` - End session
- `/barcode_kiosk/validate_operation` - Validate picking

## Troubleshooting

### Scanner Not Working
- Ensure scanner is in keyboard emulation mode
- Check that scanner adds Enter/Return after barcode
- Test scanner in a text editor first

### Products Not Found
- Verify product has barcode set
- Check barcode matches exactly
- Ensure product is in the current operation

### Session Timeout
- Adjust timeout in settings
- Sessions auto-close after configured period
- Can be reopened by managers

## Support

For issues, questions, or feature requests, please contact:
- Email: support@yourcompany.com
- Website: https://www.yourcompany.com

## License

LGPL-3

## Credits

Developed by Your Company
Version 18.0.1.0.0