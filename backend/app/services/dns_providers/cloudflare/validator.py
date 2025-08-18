import json
import logging
import time
from typing import Tuple

import dns.resolver
import requests

logger = logging.getLogger(__name__)


class CloudflareTokenTester:
    def __init__(self, api_token: str, domain: str = None, headers: dict = None):
        logger.debug(f"CloudflareTokenTester received api_token: {api_token}")
        logger.debug(f"CloudflareTokenTester api_token type: {type(api_token)}")
        self.api_token = api_token
        self.domain = domain
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = (
            headers
            if headers
            else {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }
        )
        self.zone_id = None
        self.test_records_created = []

    def _make_request(
        self, method: str, endpoint: str, data: dict = None
    ) -> Tuple[bool, dict]:
        """Make API request to Cloudflare."""
        url = f"{self.base_url}{endpoint}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=self.headers)
            elif method.upper() == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=self.headers)
            else:
                return False, {"error": f"Unsupported method: {method}"}

            result = response.json()

            if response.status_code == 200 and result.get("success", False):
                return True, result
            else:
                return False, result

        except requests.exceptions.RequestException as e:
            return False, {"error": f"Request failed: {str(e)}"}
        except json.JSONDecodeError as e:
            return False, {"error": f"Invalid JSON response: {str(e)}"}

    def test_token_validity(self) -> bool:
        """Test 1: Verify the token is valid and active."""
        logger.debug("🔍 Testing token validity...")

        success, result = self._make_request("GET", "/user/tokens/verify")

        if success:
            status = result.get("result", {}).get("status")
            if status == "active":
                logger.debug("✅ Token is valid and active")
                return True
            else:
                logger.debug(f"❌ Token status: {status}")
                return False
        else:
            logger.debug(
                f"❌ Token validation failed: "
                f"{result.get('errors', [{}]).get('message', 'Unknown error')}"
            )
            return False

    def test_zone_access(self) -> bool:
        """Test 2: Verify token can list zones and find the target domain."""
        logger.debug("🔍 Testing zone access...")

        success, result = self._make_request("GET", "/zones")

        if not success:
            error_msg = result.get("errors", [{}]).get("message", "Unknown error")
            logger.debug(f"❌ Failed to list zones: {error_msg}")
            return False

        zones = result.get("result", [])

        if not zones:
            logger.debug("❌ No zones found - token may not have zone access")
            return False

        logger.debug(f"✅ Token can access {len(zones)} zone(s)")

        # If domain specified, find it
        if self.domain:
            for zone in zones:
                if zone["name"] == self.domain:
                    self.zone_id = zone["id"]
                    logger.debug(
                        f"✅ Found target domain: {self.domain} (Zone ID: {self.zone_id})"
                    )
                    return True

            logger.debug(
                f"❌ Target domain '{self.domain}' not found in accessible zones"
            )
            logger.debug("Available zones:")
            for zone in zones:
                logger.debug(f"  - {zone['name']} ({zone['id']})")
            return False
        else:
            # Use first zone if no domain specified
            self.zone_id = zones["id"]
            self.domain = zones["name"]
            logger.debug(
                f"✅ Using first available zone: {self.domain} (Zone ID: {self.zone_id})"
            )
            return True

    def test_dns_record_read(self) -> bool:
        """Test 3: Verify token can read DNS records."""
        logger.debug("🔍 Testing DNS record read permissions...")

        if not self.zone_id:
            logger.debug("❌ No zone ID available")
            return False

        success, result = self._make_request(
            "GET", f"/zones/{self.zone_id}/dns_records"
        )

        if success:
            records = result.get("result", [])
            logger.debug(f"✅ Successfully read {len(records)} DNS records")
            return True
        else:
            error_msg = result.get("errors", [{}]).get("message", "Unknown error")
            logger.debug(f"❌ Failed to read DNS records: {error_msg}")
            return False

    def test_dns_record_create_delete(self) -> bool:
        """Test 4: Verify token can create and delete DNS records."""
        logger.debug("🔍 Testing DNS record create/delete permissions...")

        if not self.zone_id:
            logger.debug("❌ No zone ID available")
            return False

        # Create a test TXT record
        test_name = f"cf-token-test.{self.domain}"
        test_content = "cloudflare-token-test-record"

        record_data = {
            "type": "TXT",
            "name": test_name,
            "content": test_content,
            "ttl": 120,
        }

        # Create record
        success, result = self._make_request(
            "POST", f"/zones/{self.zone_id}/dns_records", record_data
        )

        if not success:
            error_msg = result.get("errors", [{}]).get("message", "Unknown error")
            logger.debug(f"❌ Failed to create test DNS record: {error_msg}")
            return False

        record_id = result.get("result", {}).get("id")
        if not record_id:
            logger.debug("❌ No record ID returned after creation")
            return False

        logger.debug(f"✅ Successfully created test TXT record: {test_name}")
        self.test_records_created.append(record_id)

        # Delete record
        success, result = self._make_request(
            "DELETE", f"/zones/{self.zone_id}/dns_records/{record_id}"
        )

        if success:
            logger.debug("✅ Successfully deleted test TXT record")
            self.test_records_created.remove(record_id)
            return True
        else:
            error_msg = result.get("errors", [{}]).get("message", "Unknown error")
            logger.debug(f"❌ Failed to delete test DNS record: {error_msg}")
            return False

    def test_acme_challenge_simulation(self) -> bool:
        """Test 5: Simulate ACME challenge by creating _acme-challenge record."""
        logger.debug("🔍 Testing ACME challenge simulation...")

        if not self.zone_id:
            logger.debug("❌ No zone ID available")
            return False

        # Create ACME challenge record
        acme_name = f"_acme-challenge.{self.domain}"
        acme_content = "test-acme-challenge-token-verification"

        record_data = {
            "type": "TXT",
            "name": acme_name,
            "content": acme_content,
            "ttl": 120,
        }

        # Create ACME challenge record
        success, result = self._make_request(
            "POST", f"/zones/{self.zone_id}/dns_records", record_data
        )

        if not success:
            error_msg = result.get("errors", [{}]).get("message", "Unknown error")
            logger.debug(f"❌ Failed to create ACME challenge record: {error_msg}")
            return False

        record_id = result.get("result", {}).get("id")
        if not record_id:
            logger.debug("❌ No record ID returned after ACME record creation")
            return False

        logger.debug(f"✅ Successfully created ACME challenge record: {acme_name}")
        self.test_records_created.append(record_id)

        # Wait a moment for DNS propagation
        logger.debug("⏳ Waiting 10 seconds for DNS propagation...")
        time.sleep(10)

        # Try to resolve the record
        try:
            resolver = dns.resolver.Resolver()
            answers = resolver.resolve(acme_name, "TXT")

            found_content = False
            for answer in answers:
                if acme_content in str(answer):
                    found_content = True
                    break

            if found_content:
                logger.debug("✅ ACME challenge record successfully resolved via DNS")
            else:
                logger.debug(
                    "⚠️  ACME challenge record created but content not found in DNS "
                    "(may need more time to propagate)"
                )

        except Exception as e:
            logger.debug(f"⚠️  Could not resolve ACME challenge record via DNS: {e}")
            logger.debug("   (This may be normal if DNS hasn't propagated yet)")

        # Clean up ACME challenge record
        success, result = self._make_request(
            "DELETE", f"/zones/{self.zone_id}/dns_records/{record_id}"
        )

        if success:
            logger.debug("✅ Successfully deleted ACME challenge record")
            self.test_records_created.remove(record_id)
            return True
        else:
            error_msg = result.get("errors", [{}]).get("message", "Unknown error")
            logger.debug(f"❌ Failed to delete ACME challenge record: {error_msg}")
            return False

    def cleanup_test_records(self):
        """Clean up any test records that weren't deleted."""
        if self.test_records_created:
            logger.debug("🧹 Cleaning up remaining test records...")
            for record_id in self.test_records_created[:]:
                success, _ = self._make_request(
                    "DELETE", f"/zones/{self.zone_id}/dns_records/{record_id}"
                )
                if success:
                    logger.debug(f"✅ Cleaned up record {record_id}")
                    self.test_records_created.remove(record_id)
                else:
                    logger.debug(f"❌ Failed to clean up record {record_id}")

    def run_all_tests(self) -> bool:
        """Run all tests and return overall success."""
        logger.debug("🚀 Starting Cloudflare DNS Token Test for ACME/Let's Encrypt")
        logger.debug("=" * 60)

        tests = [
            ("Token Validity", self.test_token_validity),
            ("Zone Access", self.test_zone_access),
            ("DNS Record Read", self.test_dns_record_read),
            ("DNS Record Create/Delete", self.test_dns_record_create_delete),
            ("ACME Challenge Simulation", self.test_acme_challenge_simulation),
        ]

        results = []

        try:
            for test_name, test_func in tests:
                logger.debug(f"\n📋 Test: {test_name}")
                result = test_func()
                results.append(result)

                if not result:
                    logger.debug(
                        f"❌ Test '{test_name}' failed - stopping further tests"
                    )
                    break

        except KeyboardInterrupt:
            logger.debug("\n⚠️  Tests interrupted by user")
            return False
        finally:
            self.cleanup_test_records()

        logger.debug("\n" + "=" * 60)
        logger.debug("📊 TEST RESULTS SUMMARY")
        logger.debug("=" * 60)

        passed = sum(results)
        total = len(results)

        for i, (test_name, _) in enumerate(tests):
            if i < len(results):
                status = "✅ PASS" if results[i] else "❌ FAIL"
                logger.debug(f"{status} {test_name}")
            else:
                logger.debug(f"⏭️  SKIP {test_name}")

        logger.debug(f"\nOverall: {passed}/{total} tests passed")

        if passed == total:
            logger.debug(
                "🎉 SUCCESS: Token is fully compatible with ACME/Let's Encrypt!"
            )
            logger.debug(
                "   Your token has all required permissions for DNS-01 challenges."
            )
            return True
        else:
            logger.debug("❌ FAILURE: Token is not compatible with ACME/Let's Encrypt")
            logger.debug("   Please check token permissions and try again.")
            return False
