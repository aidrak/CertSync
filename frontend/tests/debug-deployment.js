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

        // Navigate to Deployments page
        console.log('Navigating to Deployments page...');
        await page.goto('http://localhost:8877/deployments.html', { waitUntil: 'networkidle2' });
        await page.waitForSelector('h1'); // Assuming there is an h1 tag
        const pageTitle = await page.title();
        assert.strictEqual(pageTitle, 'Deployments - CertSync', 'Should be on the Deployments page');
        console.log('Deployments page loaded successfully.');

        // Add a new Deployment
        console.log('Adding a new Deployment...');
        await page.click('#add-deployment-btn');
        await page.waitForSelector('#add-deployment-modal', { visible: true });
        console.log('"Add Deployment" modal is visible.');

        await page.select('#deployment-company', 'B-Company');
        await page.waitForSelector('#deployment-certificate option[value="1"]');
        await page.select('#deployment-certificate', '1');
        await page.waitForSelector('#deployment-target-system option[value="1"]');
        await page.select('#deployment-target-system', '1');
        await page.click('button[type="submit"]');

        // Wait for the modal to close
        await page.waitForSelector('#add-deployment-modal', { hidden: true });
        console.log('Deployment added successfully.');

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