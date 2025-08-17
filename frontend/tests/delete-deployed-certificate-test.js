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

        // Login
        await page.waitForSelector('#username');
        await page.type('#username', 'admin');
        await page.type('#password', 'password');
        await page.click('button[type="submit"]');
        await page.waitForSelector('.sidebar', { timeout: 30000 });
        console.log('Login successful.');

        // Using an existing target system and certificate for this test
        console.log('Using existing target system and certificate.');

        // Add a new deployment
        console.log('Navigating to Deployments page...');
        await page.goto('http://localhost:8877/deployments.html', { waitUntil: 'networkidle2' });
        await page.click('#add-deployment-btn');
        await page.waitForSelector('#add-deployment-modal', { visible: true });
        await page.select('#deployment-certificate', '1'); // Assuming cert ID 1 exists
        await page.select('#deployment-target-system', '1'); // Assuming target system ID 1 exists
        await page.waitForSelector('#save-deployment-btn', { visible: true });
        await page.click('#save-deployment-btn');
        await page.waitForSelector('#add-deployment-modal', { hidden: true });
        console.log('Deployment added.');

        // Attempt to delete the certificate
        console.log('Navigating to Certificates page to attempt deletion...');
        await page.goto('http://localhost:8877/certificates.html', { waitUntil: 'networkidle2' });

        page.on('dialog', async dialog => {
            console.log('Accepting confirmation dialog...');
            await dialog.accept();
        });

        await page.waitForSelector('button[data-id="1"].delete-cert-btn');
        await page.click('button[data-id="1"].delete-cert-btn');
        console.log('Delete button clicked for certificate with active deployment.');

        // Wait for the toast message
        await page.waitForSelector('.toast.error');
        const toastMessage = await page.$eval('.toast.error', el => el.textContent);
        assert.strictEqual(toastMessage, 'Cannot delete a certificate tied to an active deployment. Please delete the deployment and try again.');
        console.log('Correct error message displayed.');

        console.log('Test passed!');
    } catch (error) {
        console.error('An error occurred during the Puppeteer test:', error);
        process.exit(1);
    } finally {
        // Clean up the created deployment
        try {
            const deployments = await page.evaluate(() => {
                return fetch('/api/v1/deploy/').then(res => res.json());
            });
            const deploymentToDelete = deployments.find(d => d.certificate_id === 1 && d.target_system_id === 1);
            if (deploymentToDelete) {
                await page.evaluate((id) => {
                    return fetch(`/api/v1/deploy/${id}`, { method: 'DELETE' });
                }, deploymentToDelete.id);
                console.log('Cleaned up deployment.');
            }
        } catch (error) {
            console.error('Error during cleanup:', error);
        }

        if (browser) {
            await browser.close();
        }
    }
})();