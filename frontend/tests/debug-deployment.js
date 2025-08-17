const puppeteer = require('puppeteer');

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

        // Click the deploy button
        console.log('Clicking deploy button...');
        await page.click(".deploy-btn[data-id='2']");

        // Wait for a bit to see the result
        await new Promise(resolve => setTimeout(resolve, 5000));

        console.log('Deployment initiated.');

    } catch (error) {
        console.error('An error occurred during the Puppeteer test:', error);
        process.exit(1);
    } finally {
        if (browser) {
            await browser.close();
        }
    }
})();