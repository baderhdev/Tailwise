"""Rerun the full Tailwise pipeline: python run.py [--refresh]  (--refresh re-downloads from yfinance)."""
import sys

from tailwise import allocation, benchmark, covariance, data, eda, regimes, stress, var

if __name__ == "__main__":
    data.run(refresh="--refresh" in sys.argv)
    eda.run()
    benchmark.run()
    covariance.run()
    var.run()
    regimes.run()
    stress.run()
    allocation.run()
