"""
Provision a host for the two-tier app — no Docker.

  Tier 1: Flask app, run by gunicorn under a systemd service.
  Tier 2: MySQL server (created/configured by this script).
  Nginx sits in front as a reverse proxy on port 80.

Run with:  sudo python3 setup_host.py   (on Ubuntu/Debian)
"""
import subprocess
import os


def run(cmd):
    subprocess.run(cmd, shell=True, check=True)


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(PROJECT_DIR, "app")
VENV_DIR = os.path.join(PROJECT_DIR, "venv")

# Data-tier settings (override via the environment before running if desired)
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "user_profile")
MYSQL_USER = os.environ.get("MYSQL_USER", "appuser")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "apppassword")

# 1. Install system packages: Nginx + Python tooling + MySQL server
run("sudo apt-get update")
run("sudo apt-get install -y nginx python3-venv python3-pip "
    "mysql-server default-libmysqlclient-dev build-essential")
run("sudo systemctl enable --now nginx")
run("sudo systemctl enable --now mysql")

# 2. Create the database + application user (Tier 2)
sql = (
    f"CREATE DATABASE IF NOT EXISTS {MYSQL_DATABASE} "
    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; "
    f"CREATE USER IF NOT EXISTS '{MYSQL_USER}'@'localhost' "
    f"IDENTIFIED BY '{MYSQL_PASSWORD}'; "
    f"GRANT ALL PRIVILEGES ON {MYSQL_DATABASE}.* TO '{MYSQL_USER}'@'localhost'; "
    f"FLUSH PRIVILEGES;"
)
run(f'sudo mysql -e "{sql}"')

# 3. Create a virtualenv and install the app tier's dependencies
if not os.path.exists(VENV_DIR):
    run(f"python3 -m venv {VENV_DIR}")
run(f"{VENV_DIR}/bin/pip install --upgrade pip")
run(f"{VENV_DIR}/bin/pip install -r {APP_DIR}/requirements.txt")

# 4. Ensure a .env exists (systemd reads it for DB creds / secret key)
env_path = os.path.join(PROJECT_DIR, ".env")
if not os.path.exists(env_path):
    with open(env_path, "w") as fh:
        fh.write(
            "ADMIN_USER=admin\n"
            "ADMIN_PASSWORD=admin\n"
            "SECRET_KEY=change-me-in-prod\n"
            "MYSQL_HOST=127.0.0.1\n"
            "MYSQL_PORT=3306\n"
            f"MYSQL_DATABASE={MYSQL_DATABASE}\n"
            f"MYSQL_USER={MYSQL_USER}\n"
            f"MYSQL_PASSWORD={MYSQL_PASSWORD}\n"
        )

# 5. Install a systemd service for the Flask app tier (gunicorn)
service = f"""[Unit]
Description=it-defined.com Flask app (two-tier, app tier)
After=network.target mysql.service
Wants=mysql.service

[Service]
WorkingDirectory={APP_DIR}
EnvironmentFile={env_path}
ExecStartPre={VENV_DIR}/bin/python -c "from app import init_db; init_db()"
ExecStart={VENV_DIR}/bin/gunicorn --bind 127.0.0.1:5000 --workers 3 app:app
Restart=always

[Install]
WantedBy=multi-user.target
"""
unit_path = "/tmp/it-defined.service"
with open(unit_path, "w") as fh:
    fh.write(service)
run(f"sudo cp {unit_path} /etc/systemd/system/it-defined.service")
run("sudo systemctl daemon-reload")
run("sudo systemctl enable --now it-defined")
run("sudo systemctl restart it-defined")

# 6. Configure Nginx as a reverse proxy to the app tier.
#    The shared it-defined.com.conf proxies to "app:5000" (the Docker service
#    name); on a bare host the app listens on 127.0.0.1:5000, so swap it.
host_conf = "/etc/nginx/sites-available/it-defined.com"
run(f"sudo cp {PROJECT_DIR}/it-defined.com.conf {host_conf}")
run(f"sudo sed -i 's#http://app:5000#http://127.0.0.1:5000#' {host_conf}")
run(f"sudo ln -sf {host_conf} /etc/nginx/sites-enabled/it-defined.com")
run("sudo rm -f /etc/nginx/sites-enabled/default")
run("sudo nginx -t && sudo systemctl reload nginx")

print("\nDone. MySQL data tier + gunicorn app tier (systemd) running; Nginx proxying on :80.")
