# Puppeteer Testing Notes

This document contains a log of observations, issues, and fixes related to the Puppeteer testing of the CertSync frontend.

## Session 1: Initial Setup and Testing

- **Initial test run failed.**
  - **Issue**: Timeout waiting for `#username` selector on the login page.
  - **Cause**: The URL in the test script was incorrect (had an extra `/src` in the path).
  - **Fix**: Corrected the login URL in `puppeteer-test.js`.

- **DNS page navigation test failed.**
  - **Issue**: Assertion error on the page title.
  - **Cause**: The expected title in the test was 'CertSync - DNS Management', but the actual title is 'DNS - CertSync'.
  - **Fix**: Corrected the expected title in `puppeteer-test.js`.

- **Certificates page button test passed.**
  - Verified functionality of "Add Certificate", "Download", and "Delete" buttons.
  - Modals for adding a certificate and downloading with a password appear and close correctly.
  - The confirmation dialog for deleting a certificate is handled correctly.

- **DNS Providers page button test passed.**
  - Verified functionality of "Add DNS Provider", "Test Credentials", "Edit", and "Delete" buttons.
  - Modals for adding and editing a DNS provider appear and close correctly.
  - The confirmation dialog for deleting a DNS provider is handled correctly.

- **Target Systems page button test passed.**
  - Verified functionality of "Add Target System", "Test Connection", "Edit", and "Delete" buttons.
  - **NOTE**: Modal close buttons on this page are problematic for Puppeteer's standard `.click()` method.
  - **FIX**: Used `page.evaluate()` to programmatically click the close buttons, which resolved the issue.

- **Deployments page button test passed.**
  - Verified functionality of "Add Deployment", "Deploy", "Verify VPN", and "Delete" buttons.
  - Modals for adding a deployment and viewing deployment progress appear and close correctly.
  - The confirmation dialog for deleting a deployment is handled correctly.

- **Console and network logging test passed.**
  - Successfully captured console logs and network requests during the test run.
  - Verified that the "Add Target System" functionality is working correctly for SonicWall devices.
  - The test was able to fill out the form, test the connection, and save the new target system.