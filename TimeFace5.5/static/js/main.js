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

// Device status monitoring with lazy loading
function startDeviceStatusMonitoring() {
    deviceStatusInterval = setInterval(updateDeviceStatus, 30000);
    // Load device info asynchronously on page load
    loadDeviceInfoAsync();
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
                
                // Update device info if available
                updateDeviceInfoDisplay(device);
            });
        })
        .catch(error => console.error('Error updating device status:', error));
}

function loadDeviceInfoAsync() {
    // Get all device cards and load their info asynchronously
    const deviceCards = document.querySelectorAll('[data-device-id]');
    
    deviceCards.forEach((card, index) => {
        const deviceId = card.dataset.deviceId;
        if (deviceId) {
            // Stagger requests to avoid overwhelming the server
            setTimeout(() => {
                loadSingleDeviceInfo(deviceId);
            }, index * 500); // 500ms delay between requests
        }
    });
}

function loadSingleDeviceInfo(deviceId) {
    fetch(`/api/devices/${deviceId}/info`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateDeviceInfoDisplay({
                    id: deviceId,
                    ...data.data
                });
            }
        })
        .catch(error => console.error(`Error loading device ${deviceId} info:`, error));
}

function updateDeviceInfoDisplay(device) {
    const deviceCard = document.querySelector(`[data-device-id="${device.id}"]`);
    if (!deviceCard) return;
    
    // Update user count
    const userCountElement = deviceCard.querySelector('.user-count');
    if (userCountElement && device.user_count !== undefined) {
        userCountElement.textContent = device.user_count;
    }
    
    // Update template count
    const templateCountElement = deviceCard.querySelector('.template-count');
    if (templateCountElement && device.template_count !== undefined) {
        templateCountElement.textContent = device.template_count;
    }
    
    // Update face count
    const faceCountElement = deviceCard.querySelector('.face-count');
    if (faceCountElement && device.face_count !== undefined) {
        faceCountElement.textContent = device.face_count;
    }
    
    // Update log count
    const logCountElement = deviceCard.querySelector('.log-count');
    if (logCountElement && device.log_count !== undefined) {
        logCountElement.textContent = device.log_count;
    }
    
    // Update device time
    const timeElement = deviceCard.querySelector('.device-time');
    if (timeElement && device.device_time) {
        timeElement.textContent = device.device_time;
    }
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

// Device info loading function for devices page
function loadDeviceInfo(deviceId) {
    const deviceInfoDiv = document.getElementById(`device-info-${deviceId}`);
    const loadingSpinner = deviceInfoDiv.querySelector('.loading-spinner');
    const deviceInfoContent = deviceInfoDiv.querySelector('.device-info-content');
    
    // Show loading state
    loadingSpinner.style.display = 'block';
    deviceInfoContent.style.display = 'none';
    
    // Add timeout to prevent hanging
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
    
    // Use the correct backend route: /api/devices/<id>/info
    fetch(`/api/devices/${deviceId}/info`, {
        signal: controller.signal
    })
        .then(response => {
            clearTimeout(timeoutId);
            return response.json();
        })
        .then(data => {
            if (data.success) {
                const info = data.data || data.device_info || {};
                deviceInfoContent.innerHTML = `
                    <div class="row">
                        <div class="col-md-3">
                            <span class="badge bg-primary">${info.user_count || 0} Users</span>
                        </div>
                        <div class="col-md-3">
                            <span class="badge bg-info">${info.template_count || 0} Templates</span>
                        </div>
                        <div class="col-md-3">
                            <span class="badge bg-warning">${info.face_count || 0} Faces</span>
                        </div>
                        <div class="col-md-3">
                            <span class="badge bg-success">${info.log_count || 0} Logs</span>
                        </div>
                    </div>
                    <div class="mt-2">
                        <small class="text-muted">Device Time: ${info.device_time || 'N/A'}</small>
                    </div>
                `;
            } else {
                const msg = data.message || 'Failed to load device info';
                deviceInfoContent.innerHTML = `<div class="alert alert-danger">Error: ${msg}</div>`;
            }
        })
        .catch(error => {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                deviceInfoContent.innerHTML = `<div class="alert alert-warning">Request timeout - device may be slow to respond</div>`;
            } else {
                deviceInfoContent.innerHTML = `<div class="alert alert-danger">Error loading device info: ${error.message || error}</div>`;
            }
        })
        .finally(() => {
            loadingSpinner.style.display = 'none';
            deviceInfoContent.style.display = 'block';
        });
}

// Make loadDeviceInfo globally available
window.loadDeviceInfo = loadDeviceInfo;

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
