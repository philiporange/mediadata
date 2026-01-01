#!/usr/bin/env python3
"""
Test runner for mediadata with coverage reporting.

This script runs the full test suite with coverage analysis and generates
an HTML coverage report in /tmp for easy viewing.
"""

import sys
import subprocess
import shutil
import tempfile
from pathlib import Path


def cleanup_coverage_dirs():
    """Clean up any existing coverage directories in /tmp."""
    tmp_path = Path("/tmp")
    coverage_dirs = list(tmp_path.glob("mediadata_coverage_*"))
    
    for coverage_dir in coverage_dirs:
        if coverage_dir.is_dir():
            print(f"🧹 Cleaning up old coverage directory: {coverage_dir}")
            shutil.rmtree(coverage_dir)


def run_tests_with_coverage():
    """Run tests with coverage analysis."""
    project_root = Path(__file__).parent
    
    # Create temporary coverage directory
    coverage_dir = Path(tempfile.mkdtemp(prefix="mediadata_coverage_", dir="/tmp"))
    htmlcov_dir = coverage_dir / "htmlcov"
    
    print("🧪 Running mediadata test suite with coverage analysis")
    print("=" * 60)
    print(f"Project root: {project_root}")
    print(f"Coverage output: {coverage_dir}")
    print()
    
    try:
        # Run pytest with coverage
        cmd = [
            sys.executable, "-m", "pytest",
            "--cov=mediadata",
            f"--cov-report=html:{htmlcov_dir}",
            "--cov-report=term-missing",
            "--cov-report=json",
            "-v",
            "tests/"
        ]
        
        print("🚀 Executing command:")
        print(" ".join(cmd))
        print()
        
        # Run the command
        result = subprocess.run(cmd, cwd=project_root, capture_output=False)
        
        print()
        print("=" * 60)
        
        if result.returncode == 0:
            print("✅ All tests passed!")
            
            # Check if HTML coverage was generated
            if htmlcov_dir.exists() and (htmlcov_dir / "index.html").exists():
                print(f"📊 Coverage report generated: {htmlcov_dir}/index.html")
                print(f"   View with: firefox {htmlcov_dir}/index.html")
                
                # Show coverage summary
                coverage_json = coverage_dir / "coverage.json"
                if coverage_json.exists():
                    import json
                    try:
                        with open(coverage_json) as f:
                            cov_data = json.load(f)
                        
                        total_coverage = cov_data.get("totals", {}).get("percent_covered", 0)
                        print(f"📈 Overall coverage: {total_coverage:.1f}%")
                        
                        # Show per-file coverage
                        files = cov_data.get("files", {})
                        if files:
                            print("\n📋 Coverage by file:")
                            for filename, file_data in sorted(files.items()):
                                if filename.startswith("mediadata/"):
                                    coverage_pct = file_data.get("summary", {}).get("percent_covered", 0)
                                    print(f"  {filename}: {coverage_pct:.1f}%")
                                    
                    except Exception as e:
                        print(f"⚠️  Could not parse coverage JSON: {e}")
            else:
                print("⚠️  HTML coverage report not generated")
                
        else:
            print(f"❌ Tests failed with exit code {result.returncode}")
            
        print(f"\n💡 Coverage files will remain at: {coverage_dir}")
        print("   (Will be cleaned up on next run)")
        
        return result.returncode == 0
        
    except KeyboardInterrupt:
        print("\n⏹️  Test run interrupted by user")
        return False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


def check_dependencies():
    """Check that required testing dependencies are installed."""
    required_packages = ["pytest", "pytest-cov"]
    missing = []
    
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing.append(package)
    
    if missing:
        print("❌ Missing required testing dependencies:")
        for pkg in missing:
            print(f"  - {pkg}")
        print(f"\nInstall with: pip install {' '.join(missing)}")
        return False
    
    return True


def main():
    """Main test runner entry point."""
    print("🧪 MediaData Test Runner")
    print("=" * 40)
    
    # Clean up old coverage directories first
    cleanup_coverage_dirs()
    
    # Check dependencies
    if not check_dependencies():
        return 1
    
    # Run tests
    success = run_tests_with_coverage()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())