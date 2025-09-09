# Overview

This is a Flask-based attendance management system designed to integrate with ZKTeco biometric devices (S922W and G3 Face models). The system provides comprehensive device management, real-time attendance logging, employee administration, and automated data synchronization capabilities. It features a web-based dashboard for monitoring attendance data, managing biometric devices, and handling employee records with biometric templates.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Architecture
- **Framework**: Python Flask with SQLAlchemy ORM for database operations
- **Database**: SQLite as the primary database with configurable connection pooling
- **Authentication**: Flask-Login for session management with admin user authentication
- **Device Integration**: ZKTeco device communication using pyzk library for biometric device connectivity
- **Background Processing**: APScheduler for automated tasks like CSV exports and employee synchronization
- **Logging**: Python logging module with configurable log levels

## Frontend Architecture
- **Template Engine**: Jinja2 templates with Bootstrap 5 for responsive UI
- **Styling**: Bootstrap dark theme with Font Awesome icons and Chart.js for data visualization
- **JavaScript**: Vanilla JavaScript for real-time updates and AJAX operations
- **Real-time Updates**: Polling-based device status monitoring with configurable intervals

## Data Model Design
- **Core Entities**: Areas, Devices, Users, AttendanceLog with relational mapping
- **Biometric Storage**: Binary template storage for fingerprints and face data
- **Configuration Management**: AppSetting model for dynamic system configuration
- **Admin Management**: Separate AdminUser model for system authentication

## Device Management Architecture
- **Connection Pooling**: Persistent device connections with automatic reconnection handling
- **Status Monitoring**: Real-time device online/offline status tracking
- **Synchronization**: Bi-directional sync for user data, templates, and attendance logs
- **Error Handling**: Comprehensive error handling for device communication failures

## Automation Features
- **Scheduled Exports**: Automated CSV export every 30 minutes with configurable paths
- **Employee Sync**: Daily synchronization from external CSV sources for active/terminated employees
- **Device Sync**: Automatic pushing of user data and biometric templates to assigned devices

# External Dependencies

## Core Libraries
- **Flask**: Web framework with SQLAlchemy extension for database operations
- **pyzk**: ZKTeco device communication library for biometric device integration
- **pandas**: Data manipulation for CSV export/import operations
- **APScheduler**: Background task scheduling for automated processes
- **Werkzeug**: WSGI utilities and security functions

## Frontend Dependencies
- **Bootstrap 5**: CSS framework with dark theme support
- **Font Awesome**: Icon library for UI components
- **Chart.js**: JavaScript charting library for dashboard visualizations

## Device Integration
- **ZKTeco Devices**: S922W and G3 Face biometric devices via TCP/IP communication
- **Network Communication**: Direct IP-based device connectivity on configurable ports

## File System Integration
- **CSV Import/Export**: Configurable file paths for employee data and attendance exports
- **Template Storage**: Binary storage for biometric templates in database
- **Configuration Files**: Environment-based configuration for database and security settings

## Database Configuration
- **SQLite**: Default database with support for connection pooling and pre-ping health checks
- **Environment Variables**: Configurable database URL and session secrets
- **Migration Support**: Automatic table creation with SQLAlchemy model definitions