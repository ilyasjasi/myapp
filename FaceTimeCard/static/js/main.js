// Main JavaScript file for ZKTeco Attendance Management System

// Global variables
let deviceStatusInterval;

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    // Start device status monitoring if on dashboard
    if (window.location.pathname === '/') {
        startDeviceStatusMonitoring();
    }
    
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });
});

// Device status monitoring
function startDeviceStatusMonitoring() {
    deviceStatusInterval = setInterval(updateDeviceStatus, 30000);
}

function updateDeviceStatus() {
    fetch('/api/devices/status')
        .then(response => response.json())
        .then(devices => {
            devices.forEach(device => {
                const statusElement = document.querySelector(`[data-device-id="${device.id}"] .badge`);
                if (statusElement) {
                    statusElement.className = `badge bg-${device.online_status ? 'success' : 'danger'}`;
                    statusElement.textContent = device.online_status ? 'Online' : 'Offline';
                }
            });
        })
        .catch(error => console.error('Error updating device status:', error));
}

// Utility functions
function showToast(message, type = 'success') {
    // Create toast element
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    const bootstrapToast = new bootstrap.Toast(toast);
    bootstrapToast.show();
    
    // Remove toast after it's hidden
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '11';
    document.body.appendChild(container);
    return container;
}

// Form validation
function validateIPAddress(ip) {
    const ipRegex = /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
    return ipRegex.test(ip);
}

// API helper functions
function makeApiCall(url, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        }
    };
    
    if (data) {
        options.body = JSON.stringify(data);
    }
    
    return fetch(url, options)
        .then(response => response.json())
        .then(data => {
            if (data.success === false) {
                throw new Error(data.message || 'Operation failed');
            }
            return data;
        });
}

// Loading state management
function setButtonLoading(button, loading = true) {
    if (loading) {
        button.dataset.originalText = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
        button.disabled = true;
    } else {
        button.innerHTML = button.dataset.originalText || button.innerHTML;
        button.disabled = false;
    }
}

// Date formatting
function formatDateTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString();
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString();
}

// Export functions for global use
window.AttendanceApp = {
    showToast,
    validateIPAddress,
    makeApiCall,
    setButtonLoading,
    formatDateTime,
    formatDate,
    updateDeviceStatus
};
