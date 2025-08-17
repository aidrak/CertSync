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

        // Navigate to Certificates page
        console.log('Navigating to Certificates page...');
        await page.goto('http://localhost:8877/certificates.html', { waitUntil: 'networkidle2' });
        await page.waitForSelector('h1'); // Assuming there is an h1 tag
        const pageTitle = await page.title();
        assert.strictEqual(pageTitle, 'Certificates - CertSync', 'Should be on the Certificates page');
        console.log('Certificates page loaded successfully.');

        // Delete the first certificate
        console.log('Attempting to delete the first certificate...');
        await page.waitForSelector('.delete-cert-btn');
        
        // Handle the confirmation dialog
        page.on('dialog', async dialog => {
            console.log('Accepting confirmation dialog...');
            await dialog.accept();
        });

        await page.click('.delete-cert-btn');
        
        console.log('Delete button clicked.');

        // Wait for a moment to allow the deletion to process
        await new Promise(resolve => setTimeout(resolve, 2000));

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