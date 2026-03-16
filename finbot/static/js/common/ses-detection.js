/**
 * SES Lockdown Detection & Info
 * 
 * Optional script to detect and inform developers about SES lockdown
 * presence from browser extensions (MetaMask, etc.)
 * 
 * Usage: Add to base template as the first script tag if desired:
 * <script src="{{ url_for('static', path='js/common/ses-detection.js') }}"></script>
 */

(function() {
    'use strict';
    
    // Check if SES lockdown is present
    const hasLockdown = typeof window.lockdown !== 'undefined';
    const hasSES = typeof window.SES !== 'undefined';
    
    if (hasLockdown || hasSES) {
        // Only log if developer tools are open (don't spam production console)
        const isDevelopment = window.location.hostname === 'localhost' || 
                            window.location.hostname === '127.0.0.1' ||
                            window.location.hostname.includes('dev');
        
        if (isDevelopment) {
            console.groupCollapsed(
                '%c🔒 SES Lockdown Detected',
                'color: #06d4ff; font-weight: bold; font-size: 12px; padding: 4px;'
            );
            
            console.info(
                '%cSource: Browser Extension (likely MetaMask or crypto wallet)',
                'color: #94a3b8;'
            );
            
            console.info(
                '%cImpact: Harmless console warnings about "unpermitted intrinsics"',
                'color: #94a3b8;'
            );
            
            console.info(
                '%cAction: Safe to ignore - does not affect FinBot functionality',
                'color: #10b981;'
            );
            
            if (hasLockdown) {
                console.info('Detected: window.lockdown');
            }
            if (hasSES) {
                console.info('Detected: window.SES');
            }
            
            console.info(
                '%cTo verify: Test in incognito mode with extensions disabled',
                'color: #fbbf24;'
            );
            
            console.groupEnd();
        }
    }
    
    // Suppress repetitive lockdown warnings (optional - uncomment if desired)
    /*
    const originalWarn = console.warn;
    console.warn = function(...args) {
        const message = args.join(' ');
        // Filter out SES lockdown warnings
        if (message.includes('Removing unpermitted intrinsics') ||
            message.includes('lockdown')) {
            return; // Suppress
        }
        originalWarn.apply(console, args);
    };
    */
})();
