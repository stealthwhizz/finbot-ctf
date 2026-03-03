import re
import json
import gspread
from datetime import datetime
from typing import Optional, Dict, List
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os
import pytest

# Load environment variables at module level
load_dotenv()


class GoogleSheetsReporter:
    """Handles updating a specific Google Sheets worksheet with test results."""
    
    def __init__(self, worksheet_name: str):
        """Initialize connection to a specific worksheet."""
        self.worksheet_name = worksheet_name
        self.results: List[Dict] = []
        
        # Get credentials from environment
        creds_json = os.getenv('GOOGLE_CREDENTIALS')
        sheets_id = os.getenv('GOOGLE_SHEETS_ID')
        
        if not sheets_id:
            raise ValueError("GOOGLE_SHEETS_ID not set in environment")
        
        # Authenticate with Google Sheets
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        
        if creds_json:
            # Use JSON string from environment (for CI/CD)
            creds_dict = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            # Use credentials file (for local development)
            creds_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'google-credentials.json')
            credentials = Credentials.from_service_account_file(creds_file, scopes=scopes)
        
        self.client = gspread.authorize(credentials)
        self.sheet = self.client.open_by_key(sheets_id)
        
        # Get or create worksheet
        try:
            self.worksheet = self.sheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # CHANGE: Increase cols from 10 to 13 to support columns K, L, M
            self.worksheet = self.sheet.add_worksheet(title=worksheet_name, rows=1000, cols=13)
            self._initialize_headers()
    
    def _initialize_headers(self):
        """Set up column headers if worksheet is new."""
        if self.worksheet_name == "Summary":
            headers = [
                'Timestamp',
                'Test Suite',
                'Total Tests',
                'Passed',
                'Failed',
                'Pass Rate',
                'Duration (s)',
                'Test Details',
                'Statuses'
            ]
        else:
            # Standard test case headers - NOW INCLUDES COLUMNS K, L, M
            headers = [
                'US ID',                          # Column A (1)
                'Dependency',                     # Column B (2)
                'Creator',                        # Column C (3)
                'Claimed by',                     # Column D (4)
                'Title',                          # Column E (5)
                'Description',                    # Column F (6)
                'Steps',                          # Column G (7)
                'Expected Results',               # Column H (8)
                'Actual Results',                 # Column I (9)
                'Placeholder J',                  # Column J (10)
                'Automation Status',              # Column K (11) - automation_status
                'Automation Notes',               # Column L (12) - automation_notes
                'Last Run'                        # Column M (13) - timestamp
            ]
        self.worksheet.append_row(headers)
    
    def record_result(self, test_code: str, test_name: str, status: str, duration: float, message: str = ""):
        """Record a single test result."""
        row = {
            'code': test_code,
            'name': test_name,
            'status': status,
            'duration': duration,
            'timestamp': datetime.now().isoformat(),
            'message': message
        }
        self.results.append(row)
    
    def save_results(self):
        """Save all accumulated results to the worksheet."""
        if not self.results:
            return
        
        # Update existing rows with test results
        for result in self.results:
            self._update_actual_results(result)
        
        self.results = []
    
    def _update_actual_results(self, result: dict):
        """Find test code in column A and update columns K, L, M in the same row."""
        test_code = result['code']
        status = result['status']
        duration = result['duration']
        message = result['message']
        timestamp = result['timestamp']
        
        # Format automation notes with more detail for failures
        if status == "FAILED" and message:
            # For FAILED tests, capture the full error message (up to 5000 chars)
            error_msg = message.replace('\n', ' | ')[:5000]
            automation_notes = f"Status: FAILED | Duration: {duration:.2f}s | {error_msg}"
        else:
            # For passed/skipped tests, use brief format
            automation_notes = f"Status: {status} | Duration: {duration:.2f}s"
            if message:
                automation_notes += f" | {message[:500]}"
        
        try:
            # Get all values from column A (US ID) to find matching row
            col_a_values = self.worksheet.col_values(1)
            
            # Search for test code in column A (case-insensitive, strip whitespace)
            row_number = None
            for idx, cell_value in enumerate(col_a_values, start=1):
                if cell_value and cell_value.strip().upper() == test_code.strip().upper():
                    row_number = idx
                    break
            
            if row_number:
                # Update columns K (11), L (12), M (13) in matching row
                self.worksheet.update_cell(row_number, 11, status)
                self.worksheet.update_cell(row_number, 12, automation_notes)
                self.worksheet.update_cell(row_number, 13, timestamp)
                
                print(f"✓ Updated {test_code} at row {row_number}: {status}")
                return
            else:
                # DEBUG: Print more details about unmatched tests
                print(f"\n🔴 UNMATCHED TEST DETECTED:")
                print(f"   Test Code: {test_code}")
                print(f"   Test Name: {result.get('name', 'Unknown')}")
                print(f"   Status: {status}")
                print(f"   Duration: {duration:.2f}s")
                print(f"   Worksheet: {self.worksheet_name}")
                print(f"   Message: {message[:100] if message else 'None'}")
                print(f"   Available US IDs in column A: {[v for v in col_a_values[1:11] if v]}")
                print()
                
        except Exception as e:
            print(f"⚠️ Could not update test code {test_code}: {e}")
    
    def save_summary_results(self, results_dicts: list):
        """Save summary with one row per test suite."""
        if not results_dicts:
            return
        
        # Group results by worksheet
        results_by_worksheet = {}
        for result in results_dicts:
            ws = result.get('worksheet', 'Unknown')
            if ws not in results_by_worksheet:
                results_by_worksheet[ws] = []
            results_by_worksheet[ws].append(result)
        
        # Create a summary row for each worksheet
        for worksheet_name, worksheet_results in results_by_worksheet.items():
            self._save_summary_row_for_worksheet(worksheet_name, worksheet_results)
    
    def _save_summary_row_for_worksheet(self, worksheet_name: str, results: list):
        """Create summary row for a specific worksheet."""
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r['status'] == 'PASSED')
        failed_tests = total_tests - passed_tests
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        total_duration = sum(float(r['duration']) for r in results)
        
        test_names = "\n".join([
            f"{r['code']}: {r['name']} ({r['duration']:.2f}s)"
            for r in results
        ])
        
        statuses_str = "\n".join([r['status'] for r in results])
        
        # Create row with CORRECT column order:
        # Timestamp | Total Tests | Passed | Failed | Pass Rate | Duration | Test Suite | Test Details | Statuses
        summary_row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Timestamp
            total_tests,                                    # Total Tests
            passed_tests,                                   # Passed
            failed_tests,                                   # Failed
            f"{pass_rate:.1f}%",                           # Pass Rate
            f"{total_duration:.2f}",                        # Duration
            worksheet_name,                                 # Test Suite
            test_names,                                     # Test Details
            statuses_str                                    # Statuses
        ]
        self.worksheet.insert_row(summary_row, index=2)


def extract_iso_code(docstring: Optional[str]) -> Optional[str]:
    """Extract test code from docstring (ISO-*, SSM-*, CUI-*, etc.)."""
    if not docstring:
        return None
    # Match patterns like: ISO-DAT-001, SSM-HMC-001, CUI-NS-001, etc.
    match = re.search(r'([A-Z][A-Z0-9]*-[A-Z0-9]+-\d+)', docstring)
    return match.group(1) if match else None


def detect_test_category(item) -> str:
    """Detect which Google Sheets worksheet a test belongs to based on file path."""
    fspath = str(item.fspath).lower()
    
    path_worksheet_map = {
        'complete_user_isolation': 'Complete User Isolation',
        'isolation': 'Isolation Testing Framework TCs',
        'vendor': 'Isolation Testing Framework TCs',
        'auth': 'Secure Session Management',
        'session': 'Secure Session Management',
        'security': 'Security Penetration Testing',
        'ctf': 'CTF Challenge Validation',
        'performance': 'Performance Testing',
        'browser': 'Cross_Browser',
        'e2e': 'End-To-End',
        'integration': 'End-To-End',
        'google_sheets': 'Google Sheets Integration',
        'summary': 'Summary'
    }
    
    for keyword, worksheet in path_worksheet_map.items():
        if keyword in fspath:
            return worksheet
    
    return 'Isolation Testing Framework TCs'


class GoogleSheetsPlugin:
    """Pytest plugin for automatic Google Sheets test result reporting."""
    
    # Worksheets that should have test results updated
    UPDATABLE_WORKSHEETS = {
        'Isolation Testing Framework TCs',
        'Secure Session Management',
        'Complete User Isolation'
    }
    
    def __init__(self, config):
        self.config = config
        self.reporters: Dict[str, GoogleSheetsReporter] = {}
        self.results_by_worksheet: Dict[str, List] = {}
        self.session_start_time = datetime.now()
        self.test_count = 0
        self.passed_count = 0
        self.failed_count = 0
        
        if config.getoption("--google-sheets"):
            # List of worksheets to initialize
            worksheets = [
                'Isolation Testing Framework TCs',
                'Secure Session Management',
                'Security Penetration Testing',
                'CTF Challenge Validation',
                'Performance Testing',
                'Cross_Browser',
                'End-To-End',
                'Complete User Isolation',
                'Summary',
            ]
            
            for worksheet_name in worksheets:
                try:
                    self.reporters[worksheet_name] = GoogleSheetsReporter(worksheet_name)
                    self.results_by_worksheet[worksheet_name] = []
                except Exception as e:
                    print(f"⚠️  Could not initialize worksheet '{worksheet_name}': {e}")
    
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        """Hook to capture test results and update Google Sheets."""
        outcome = yield
        report = outcome.get_result()
        
        # Only process the actual test call (not setup/teardown)
        if report.when == "call" and self.config.getoption("--google-sheets"):
            test_code = extract_iso_code(item.obj.__doc__)
            worksheet_name = detect_test_category(item)
            
            status = "PASSED" if report.passed else "FAILED"
            if report.skipped:
                status = "SKIPPED"
            
            duration = report.duration
            message = str(report.longrepr) if report.longrepr else ""
            
            # Track test counts
            self.test_count += 1
            if status == "PASSED":
                self.passed_count += 1
            elif status == "FAILED":
                self.failed_count += 1
            
            result = {
                'code': test_code or item.name,
                'name': item.name,
                'status': status,
                'duration': duration,
                'message': message,
                'worksheet': worksheet_name
            }
            
            # Track result for the specific worksheet (only if it's updatable)
            if worksheet_name in self.results_by_worksheet:
                self.results_by_worksheet[worksheet_name].append(result)
            
            # Also add to Summary
            if 'Summary' in self.results_by_worksheet:
                self.results_by_worksheet['Summary'].append(result)
    
    def pytest_sessionfinish(self, session, exitstatus):
        """Hook called after all tests complete."""
        if not self.config.getoption("--google-sheets"):
            return
        
        print("\n" + "=" * 90)
        print("📊 AUTOMATED TEST RESULTS - GOOGLE SHEETS UPDATE")
        print("=" * 90)
        
        # Calculate overall stats
        total_tests = 0
        passed_tests = 0
        
        # Save results ONLY to updatable worksheets (except Summary)
        worksheet_count = 0
        for worksheet_name, results in self.results_by_worksheet.items():
            # Only update if worksheet is in the updatable list and has results
            if results and worksheet_name != "Summary" and worksheet_name in self.UPDATABLE_WORKSHEETS:
                worksheet_count += 1
                passed_count = sum(1 for r in results if r['status'] == 'PASSED')
                total_count = len(results)
                passed_tests += passed_count
                total_tests += total_count
                
                # Save to worksheet
                if worksheet_name in self.reporters:
                    try:
                        for result in results:
                            self.reporters[worksheet_name].record_result(
                                result['code'],
                                result['name'],
                                result['status'],
                                result['duration'],
                                result['message']
                            )
                        self.reporters[worksheet_name].save_results()
                        print(f"✓ Updated {total_count} results in '{worksheet_name}' ({passed_count}/{total_count} passed)")
                    except Exception as e:
                        print(f"✗ ERROR saving to '{worksheet_name}': {e}")
        
        # Save Summary ONCE with all results at the end
        if "Summary" in self.results_by_worksheet and self.reporters.get("Summary"):
            try:
                self.reporters["Summary"].save_summary_results(self.results_by_worksheet["Summary"])
                summary_results = self.results_by_worksheet["Summary"]
                print(f"✓ Updated Summary sheet ({len(summary_results)} total tests)")
            except Exception as e:
                print(f"✗ ERROR saving to Summary: {e}")
        
        # Calculate pass rate
        if total_tests > 0:
            pass_rate = (passed_tests / total_tests) * 100
            print(f"\n📈 OVERALL RESULTS: {passed_tests}/{total_tests} passed ({pass_rate:.1f}%)")
        
        print("\n📋 WORKSHEET BREAKDOWN:")
        print("-" * 90)
        for worksheet_name, results in self.results_by_worksheet.items():
            if results and worksheet_name != "Summary":
                passed = sum(1 for r in results if r['status'] == 'PASSED')
                failed = sum(1 for r in results if r['status'] == 'FAILED')
                skipped = sum(1 for r in results if r['status'] == 'SKIPPED')
                total = len(results)
                updatable_status = "✓" if worksheet_name in self.UPDATABLE_WORKSHEETS else "⊗"
                print(f"  {updatable_status} {worksheet_name}: {passed} passed, {failed} failed, {skipped} skipped ({total} total)")
        
        elapsed_time = (datetime.now() - self.session_start_time).total_seconds()
        print(f"\n⏱️  Test Execution Time: {elapsed_time:.2f}s")
        print(f"✓ Results saved to {worksheet_count} worksheet(s)")
        print("=" * 90)


# Module-level pytest hooks (NOT indented)
def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--google-sheets",
        action="store_true",
        default=False,
        help="Enable automatic Google Sheets test result reporting"
    )


def pytest_configure(config):
    """Register the plugin."""
    config.addinivalue_line(
        "markers", "google_sheets: mark test to report to Google Sheets"
    )
    if config.getoption("--google-sheets"):
        plugin = GoogleSheetsPlugin(config)
        config.pluginmanager.register(plugin)