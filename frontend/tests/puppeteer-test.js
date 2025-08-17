const puppeteer = require('puppeteer');
const assert = require('assert');

(async () => {
    let browser;
    try {
        browser = await puppeteer.launch({
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        const page = await browser.newPage();

        // Listen for console events
        page.on('console', msg => console.log('PAGE LOG:', msg.text()));

        // Listen for network requests
        page.on('request', request => {
            console.log('>>', request.method(), request.url());
        });
        page.on('response', response => {
            console.log('<<', response.status(), response.url());
        });

        console.log('Navigating to login page...');
        await page.goto('http://localhost:8877/login.html', { waitUntil: 'networkidle2' });
        console.log('Login page loaded.');
        await new Promise(resolve => setTimeout(resolve, 2000)); // Wait for 2 seconds

        // Login
        console.log('Waiting for username field...');
        await page.waitForSelector('#username');
        console.log('Username field found. Typing username...');
        await page.type('#username', 'admin');
        console.log('Typing password...');
        await page.type('#password', 'password');
        console.log('Clicking login button...');
        await page.click('button[type="submit"]');

        // Wait for sidebar to appear
        console.log('Waiting for sidebar...');
        await page.waitForSelector('.sidebar', { timeout: 30000 });
        console.log('Login successful, sidebar is visible.');

        // Navigate to Target Systems page
        console.log('Navigating to Target Systems page...');
        await page.goto('http://localhost:8877/target_systems.html', { waitUntil: 'networkidle2' });
        await page.waitForSelector('h1'); // Assuming there is an h1 tag
        const pageTitle = await page.title();
        assert.strictEqual(pageTitle, 'Target Systems - CertSync', 'Should be on the Target Systems page');
        console.log('Target Systems page loaded successfully.');

        // Add a new SonicWall Target System
        console.log('Adding a new SonicWall Target System...');
        await page.click('#add-target-system-btn');
        await page.waitForSelector('#add-target-system-modal', { visible: true });
        console.log('"Add Target System" modal is visible.');

        await page.select('#ts-company', 'B-Company');
        await page.select('#ts-type', 'sonicwall');
        await page.type('#ts-name', 'Test-FW-02');
        await page.type('#ts-admin-username', 'admin');
        await page.type('#ts-admin-password', 'Abcde12345!');
        await page.type('#ts-public-ip', '172.20.20.232');
        await page.type('#ts-port', '443');
        await page.click('#test-connection-btn');

        // Wait for the test to complete and the save button to appear
        await page.waitForFunction(
            'document.querySelector("#test-connection-btn").textContent === "Save Target System"'
        );
        console.log('Connection test successful. Saving target system...');
        await page.click('#test-connection-btn');

        // Wait for the modal to close
        await page.waitForSelector('#add-target-system-modal', { hidden: true });
        console.log('Target system added successfully.');

        // Logout
        console.log('Clicking logout button...');
        await page.click('#sign-out-btn');
        console.log('Waiting for login form...');
        await page.waitForSelector('form', { timeout: 30000 });
        console.log('Logout successful, login form is visible.');

        console.log('Test passed!');
    } catch (error) {
        console.error('An error occurred during the Puppeteer test:', error);
        process.exit(1);
    } finally {
        if (browser) {
            await browser.close();
        }
    }
})();