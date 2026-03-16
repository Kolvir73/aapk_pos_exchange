export SMTP_HOST="smtp.yourprovider.com"
export SMTP_PORT="587"
export SMTP_USER="you@yourdomain.com"
export SMTP_PASS="your_app_or_smtp_password"
export FROM_ADDR="you@yourdomain.com"

# python3 smtp_test.py
# python3 run_exchange.py --db exchange.sqlite --year 2026 --mode smtp --dry-run
# python3 run_exchange.py --db exchange.sqlite --year 2026 --mode smtp
# DELETE FROM submissions;
