import requests
import sys
import time
import json
from datetime import datetime

class OTPSystemTester:
    def __init__(self, base_url="https://qr-verify-2.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_username = f"testuser_{int(time.time())}"
        self.test_email = f"test_{int(time.time())}@example.com"

    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")
        return success

    def test_health_check(self):
        """Test health check endpoint"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                details = f"- Status: {data.get('status')}, Service: {data.get('service')}"
            else:
                details = f"- Status Code: {response.status_code}"
                
            return self.log_test("Health Check", success, details)
        except Exception as e:
            return self.log_test("Health Check", False, f"- Error: {str(e)}")

    def test_user_registration_success(self):
        """Test successful user registration"""
        try:
            payload = {
                "username": self.test_username,
                "email": self.test_email
            }
            
            response = requests.post(f"{self.api_url}/register", json=payload, timeout=15)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                details = f"- Message: {data.get('message')}, Username: {data.get('username')}"
            else:
                try:
                    error_data = response.json()
                    details = f"- Status: {response.status_code}, Error: {error_data.get('detail')}"
                except:
                    details = f"- Status: {response.status_code}, Response: {response.text[:100]}"
                    
            return self.log_test("User Registration (Success)", success, details)
        except Exception as e:
            return self.log_test("User Registration (Success)", False, f"- Error: {str(e)}")

    def test_duplicate_username(self):
        """Test duplicate username registration"""
        try:
            payload = {
                "username": self.test_username,  # Same username as before
                "email": f"different_{int(time.time())}@example.com"
            }
            
            response = requests.post(f"{self.api_url}/register", json=payload, timeout=15)
            success = response.status_code == 400
            
            if success:
                data = response.json()
                details = f"- Correctly rejected: {data.get('detail')}"
            else:
                details = f"- Unexpected status: {response.status_code}"
                
            return self.log_test("Duplicate Username Rejection", success, details)
        except Exception as e:
            return self.log_test("Duplicate Username Rejection", False, f"- Error: {str(e)}")

    def test_duplicate_email(self):
        """Test duplicate email registration"""
        try:
            payload = {
                "username": f"different_{int(time.time())}",
                "email": self.test_email  # Same email as before
            }
            
            response = requests.post(f"{self.api_url}/register", json=payload, timeout=15)
            success = response.status_code == 400
            
            if success:
                data = response.json()
                details = f"- Correctly rejected: {data.get('detail')}"
            else:
                details = f"- Unexpected status: {response.status_code}"
                
            return self.log_test("Duplicate Email Rejection", success, details)
        except Exception as e:
            return self.log_test("Duplicate Email Rejection", False, f"- Error: {str(e)}")

    def test_get_qr_code(self):
        """Test QR code retrieval for existing user"""
        try:
            response = requests.get(f"{self.api_url}/user/{self.test_username}/qr-code", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                has_qr = 'qr_code_base64' in data and len(data['qr_code_base64']) > 0
                has_secret = 'secret' in data and len(data['secret']) > 0
                details = f"- QR Code: {'✓' if has_qr else '✗'}, Secret: {'✓' if has_secret else '✗'}"
                success = has_qr and has_secret
            else:
                try:
                    error_data = response.json()
                    details = f"- Status: {response.status_code}, Error: {error_data.get('detail')}"
                except:
                    details = f"- Status: {response.status_code}"
                    
            return self.log_test("QR Code Retrieval", success, details)
        except Exception as e:
            return self.log_test("QR Code Retrieval", False, f"- Error: {str(e)}")

    def test_qr_code_nonexistent_user(self):
        """Test QR code retrieval for non-existent user"""
        try:
            fake_username = f"nonexistent_{int(time.time())}"
            response = requests.get(f"{self.api_url}/user/{fake_username}/qr-code", timeout=10)
            success = response.status_code == 404
            
            if success:
                data = response.json()
                details = f"- Correctly returned 404: {data.get('detail')}"
            else:
                details = f"- Unexpected status: {response.status_code}"
                
            return self.log_test("QR Code Non-existent User", success, details)
        except Exception as e:
            return self.log_test("QR Code Non-existent User", False, f"- Error: {str(e)}")

    def test_password_change_invalid_user(self):
        """Test password change with invalid user"""
        try:
            payload = {
                "username": f"invalid_{int(time.time())}",
                "otp_code": "123456",
                "new_password": "newpassword123"
            }
            
            response = requests.post(f"{self.api_url}/change-password", json=payload, timeout=10)
            success = response.status_code == 404
            
            if success:
                data = response.json()
                details = f"- Correctly returned 404: {data.get('detail')}"
            else:
                details = f"- Unexpected status: {response.status_code}"
                
            return self.log_test("Password Change Invalid User", success, details)
        except Exception as e:
            return self.log_test("Password Change Invalid User", False, f"- Error: {str(e)}")

    def test_password_change_invalid_otp(self):
        """Test password change with invalid OTP"""
        try:
            payload = {
                "username": self.test_username,
                "otp_code": "000000",  # Invalid OTP
                "new_password": "newpassword123"
            }
            
            response = requests.post(f"{self.api_url}/change-password", json=payload, timeout=10)
            success = response.status_code == 400
            
            if success:
                data = response.json()
                details = f"- Correctly rejected invalid OTP: {data.get('detail')}"
            else:
                details = f"- Unexpected status: {response.status_code}"
                
            return self.log_test("Password Change Invalid OTP", success, details)
        except Exception as e:
            return self.log_test("Password Change Invalid OTP", False, f"- Error: {str(e)}")

    def test_password_change_short_password(self):
        """Test password change with short password"""
        try:
            payload = {
                "username": self.test_username,
                "otp_code": "123456",
                "new_password": "short"  # Less than 8 characters
            }
            
            response = requests.post(f"{self.api_url}/change-password", json=payload, timeout=10)
            success = response.status_code == 400
            
            if success:
                data = response.json()
                details = f"- Correctly rejected short password: {data.get('detail')}"
            else:
                details = f"- Unexpected status: {response.status_code}"
                
            return self.log_test("Password Change Short Password", success, details)
        except Exception as e:
            return self.log_test("Password Change Short Password", False, f"- Error: {str(e)}")

    def test_get_users_endpoint(self):
        """Test get users endpoint (admin)"""
        try:
            response = requests.get(f"{self.api_url}/users", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                user_count = len(data) if isinstance(data, list) else 0
                details = f"- Found {user_count} users"
                
                # Check if our test user is in the list
                test_user_found = any(user.get('username') == self.test_username for user in data)
                if test_user_found:
                    details += f", Test user found: ✓"
                else:
                    details += f", Test user found: ✗"
            else:
                details = f"- Status: {response.status_code}"
                
            return self.log_test("Get Users Endpoint", success, details)
        except Exception as e:
            return self.log_test("Get Users Endpoint", False, f"- Error: {str(e)}")

    def test_rate_limiting_registration(self):
        """Test rate limiting on registration endpoint"""
        print("\n🔄 Testing rate limiting (this may take a moment)...")
        
        try:
            # Make multiple rapid requests to trigger rate limiting
            rate_limit_email = f"ratelimit_{int(time.time())}@example.com"
            
            for i in range(6):  # Try 6 requests (limit is 5 per hour)
                payload = {
                    "username": f"ratetest_{i}_{int(time.time())}",
                    "email": rate_limit_email
                }
                
                response = requests.post(f"{self.api_url}/register", json=payload, timeout=10)
                
                if i < 5:  # First 5 should work (or fail for other reasons)
                    if response.status_code == 429:
                        # Rate limit hit earlier than expected
                        break
                else:  # 6th request should be rate limited
                    if response.status_code == 429:
                        data = response.json()
                        details = f"- Rate limit triggered correctly: {data.get('detail')}"
                        return self.log_test("Rate Limiting Registration", True, details)
                
                time.sleep(0.5)  # Small delay between requests
            
            # If we get here, rate limiting might not be working as expected
            return self.log_test("Rate Limiting Registration", False, "- Rate limit not triggered as expected")
            
        except Exception as e:
            return self.log_test("Rate Limiting Registration", False, f"- Error: {str(e)}")

    def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting OTP System Backend Tests")
        print(f"📍 Base URL: {self.base_url}")
        print(f"🔗 API URL: {self.api_url}")
        print(f"👤 Test User: {self.test_username}")
        print(f"📧 Test Email: {self.test_email}")
        print("=" * 60)
        
        # Basic connectivity
        self.test_health_check()
        
        # User registration tests
        self.test_user_registration_success()
        self.test_duplicate_username()
        self.test_duplicate_email()
        
        # QR code tests
        self.test_get_qr_code()
        self.test_qr_code_nonexistent_user()
        
        # Password change tests
        self.test_password_change_invalid_user()
        self.test_password_change_invalid_otp()
        self.test_password_change_short_password()
        
        # Admin endpoint
        self.test_get_users_endpoint()
        
        # Rate limiting (this takes longer)
        self.test_rate_limiting_registration()
        
        # Final results
        print("=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            failed = self.tests_run - self.tests_passed
            print(f"⚠️  {failed} test(s) failed")
            return 1

def main():
    tester = OTPSystemTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())