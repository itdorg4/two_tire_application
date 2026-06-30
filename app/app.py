"""
Flask portfolio app with an editable admin area, backed by SQLite.

Tier 1: Flask web/app tier — serves the portfolio, guestbook, and admin editor.
Tier 2: SQLite file — the data/persistence layer.

Public visitors see the portfolio. Logging in (default: virat / password)
unlocks an editor for the About, Work Experience, Featured Projects and
Get In Touch sections.
"""
import os
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash, session
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-prod")

# --- Admin credentials (override via env in real deployments) ---------------
ADMIN_USER = os.environ.get("ADMIN_USER", "virat")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "password")

# --- Data tier: MySQL -------------------------------------------------------
# Full URI wins if provided; otherwise build one from the discrete MYSQL_* vars.
# Falls back to a local SQLite file when no MySQL host is configured (handy for
# running the app outside Docker).
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
elif os.environ.get("MYSQL_HOST"):
    MYSQL_USER = os.environ.get("MYSQL_USER", "appuser")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "apppassword")
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "db")
    MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
    MYSQL_DB = os.environ.get("MYSQL_DATABASE", "appdb")
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    )
else:
    DB_PATH = os.environ.get(
        "DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")
    )
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"

app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Recycle/ping connections so MySQL's idle timeout doesn't break the pool.
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280}

db = SQLAlchemy(app)


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class Message(db.Model):
    """Guestbook entries."""
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class Profile(db.Model):
    """Singleton row (id=1) holding the About + Get In Touch content."""
    __tablename__ = "profile"

    id = db.Column(db.Integer, primary_key=True)
    about_p1 = db.Column(db.Text, default="")
    about_p2 = db.Column(db.Text, default="")
    contact_heading = db.Column(db.String(255), default="")
    email = db.Column(db.String(255), default="")
    location = db.Column(db.String(255), default="")
    linkedin = db.Column(db.String(255), default="")
    github = db.Column(db.String(255), default="")
    twitter = db.Column(db.String(255), default="")
    medium = db.Column(db.String(255), default="")


class Experience(db.Model):
    """A single Work Experience timeline entry."""
    __tablename__ = "experience"

    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(120), default="")
    title = db.Column(db.String(255), default="")
    company = db.Column(db.String(255), default="")
    description = db.Column(db.Text, default="")
    position = db.Column(db.Integer, default=0)


class Project(db.Model):
    """A single Featured Project card."""
    __tablename__ = "project"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), default="")
    description = db.Column(db.Text, default="")
    tags = db.Column(db.String(255), default="")  # comma-separated
    link = db.Column(db.String(255), default="")
    icon = db.Column(db.String(80), default="bi-kanban-fill")
    position = db.Column(db.Integer, default=0)


# --------------------------------------------------------------------------- #
# Auth helpers
# --------------------------------------------------------------------------- #
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            flash("Please log in to edit the profile.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_auth():
    """Expose login state to every template."""
    return {"is_admin": bool(session.get("admin"))}


# --------------------------------------------------------------------------- #
# Public routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    profile = Profile.query.get(1)
    experiences = Experience.query.order_by(Experience.position, Experience.id).all()
    projects = Project.query.order_by(Project.position, Project.id).all()
    return render_template(
        "index.html", profile=profile, experiences=experiences, projects=projects
    )


@app.route("/guestbook", methods=["GET", "POST"])
def guestbook():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        body = request.form.get("body", "").strip()

        if not (name and email and body):
            flash("All fields are required.", "danger")
            return redirect(url_for("guestbook"))

        db.session.add(Message(name=name, email=email, body=body))
        db.session.commit()
        flash("Thanks! Your message was saved.", "success")
        return redirect(url_for("guestbook"))

    messages = Message.query.order_by(Message.created_at.desc()).all()
    return render_template("guestbook.html", messages=messages)


@app.route("/healthz")
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok", "db": "up"}, 200
    except Exception as exc:  # pragma: no cover - operational path
        return {"status": "degraded", "db": "down", "error": str(exc)}, 503


# --------------------------------------------------------------------------- #
# Auth routes
# --------------------------------------------------------------------------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USER and password == ADMIN_PASSWORD:
            session["admin"] = True
            flash("Logged in. You can now edit your profile.", "success")
            nxt = request.args.get("next") or url_for("admin")
            return redirect(nxt)
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("index"))


# --------------------------------------------------------------------------- #
# Admin / editing routes
# --------------------------------------------------------------------------- #
@app.route("/admin")
@login_required
def admin():
    profile = Profile.query.get(1)
    experiences = Experience.query.order_by(Experience.position, Experience.id).all()
    projects = Project.query.order_by(Project.position, Project.id).all()
    return render_template(
        "admin.html", profile=profile, experiences=experiences, projects=projects
    )


@app.route("/admin/profile", methods=["POST"])
@login_required
def update_profile():
    """Save the About text + Get In Touch details."""
    p = Profile.query.get(1)
    p.about_p1 = request.form.get("about_p1", "").strip()
    p.about_p2 = request.form.get("about_p2", "").strip()
    p.contact_heading = request.form.get("contact_heading", "").strip()
    p.email = request.form.get("email", "").strip()
    p.location = request.form.get("location", "").strip()
    p.linkedin = request.form.get("linkedin", "").strip()
    p.github = request.form.get("github", "").strip()
    p.twitter = request.form.get("twitter", "").strip()
    p.medium = request.form.get("medium", "").strip()
    db.session.commit()
    flash("About & contact details updated.", "success")
    return redirect(url_for("admin") + "#about")


# ---- Work Experience CRUD ----
@app.route("/admin/experience/add", methods=["POST"])
@login_required
def add_experience():
    e = Experience(
        period=request.form.get("period", "").strip(),
        title=request.form.get("title", "").strip(),
        company=request.form.get("company", "").strip(),
        description=request.form.get("description", "").strip(),
        position=int(request.form.get("position") or 0),
    )
    db.session.add(e)
    db.session.commit()
    flash("Experience added.", "success")
    return redirect(url_for("admin") + "#experience")


@app.route("/admin/experience/<int:item_id>/edit", methods=["POST"])
@login_required
def edit_experience(item_id):
    e = Experience.query.get_or_404(item_id)
    e.period = request.form.get("period", "").strip()
    e.title = request.form.get("title", "").strip()
    e.company = request.form.get("company", "").strip()
    e.description = request.form.get("description", "").strip()
    e.position = int(request.form.get("position") or 0)
    db.session.commit()
    flash("Experience updated.", "success")
    return redirect(url_for("admin") + "#experience")


@app.route("/admin/experience/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_experience(item_id):
    e = Experience.query.get_or_404(item_id)
    db.session.delete(e)
    db.session.commit()
    flash("Experience deleted.", "success")
    return redirect(url_for("admin") + "#experience")


# ---- Featured Projects CRUD ----
@app.route("/admin/project/add", methods=["POST"])
@login_required
def add_project():
    p = Project(
        title=request.form.get("title", "").strip(),
        description=request.form.get("description", "").strip(),
        tags=request.form.get("tags", "").strip(),
        link=request.form.get("link", "").strip(),
        icon=request.form.get("icon", "").strip() or "bi-kanban-fill",
        position=int(request.form.get("position") or 0),
    )
    db.session.add(p)
    db.session.commit()
    flash("Project added.", "success")
    return redirect(url_for("admin") + "#projects")


@app.route("/admin/project/<int:item_id>/edit", methods=["POST"])
@login_required
def edit_project(item_id):
    p = Project.query.get_or_404(item_id)
    p.title = request.form.get("title", "").strip()
    p.description = request.form.get("description", "").strip()
    p.tags = request.form.get("tags", "").strip()
    p.link = request.form.get("link", "").strip()
    p.icon = request.form.get("icon", "").strip() or "bi-kanban-fill"
    p.position = int(request.form.get("position") or 0)
    db.session.commit()
    flash("Project updated.", "success")
    return redirect(url_for("admin") + "#projects")


@app.route("/admin/project/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_project(item_id):
    p = Project.query.get_or_404(item_id)
    db.session.delete(p)
    db.session.commit()
    flash("Project deleted.", "success")
    return redirect(url_for("admin") + "#projects")


# --------------------------------------------------------------------------- #
# DB init + default seed
# --------------------------------------------------------------------------- #
def seed_defaults():
    """Populate the original portfolio content on first run."""
    if Profile.query.get(1) is None:
        db.session.add(Profile(
            id=1,
            about_p1=("I'm a passionate DevOps Engineer who lives at the intersection of "
                      "development and operations. Over the past five years I've helped teams "
                      "ship faster and sleep better by building robust CI/CD pipelines, "
                      "containerizing applications, and managing cloud infrastructure as code."),
            about_p2=("My philosophy is simple: automate everything that's repeatable, monitor "
                      "everything that matters. I thrive on reducing deployment times, improving "
                      "system reliability, and championing a culture of collaboration."),
            contact_heading="Let's build something reliable together.",
            email="virat@example.com",
            location="Remote · Worldwide",
            linkedin="#", github="#", twitter="#", medium="#",
        ))

    if Experience.query.count() == 0:
        db.session.add_all([
            Experience(period="2023 — Present", title="Senior DevOps Engineer",
                       company="TechCorp", position=1,
                       description=("Lead the migration to Kubernetes and GitOps with ArgoCD, "
                                    "cutting deployment time by 70% and improving uptime to 99.9%.")),
            Experience(period="2021 — 2023", title="DevOps Engineer",
                       company="CloudWorks", position=2,
                       description=("Built multi-cloud Terraform modules and CI/CD pipelines "
                                    "serving 30+ microservices across AWS and Azure.")),
            Experience(period="2019 — 2021", title="Build & Release Engineer",
                       company="StartupX", position=3,
                       description=("Automated Jenkins pipelines and Dockerized legacy applications, "
                                    "reducing release cycles from weeks to hours.")),
        ])

    if Project.query.count() == 0:
        db.session.add_all([
            Project(title="GitOps Deployment Platform", icon="bi-kanban-fill", position=1,
                    description=("End-to-end GitOps workflow with ArgoCD, Helm and automated "
                                 "rollbacks on a self-hosted K8s cluster."),
                    tags="Kubernetes,ArgoCD,Helm", link="#"),
            Project(title="Infra-as-Code Toolkit", icon="bi-hdd-stack-fill", position=2,
                    description=("Reusable Terraform modules provisioning VPCs, EKS and RDS with "
                                 "zero-downtime blue/green deploys."),
                    tags="Terraform,AWS,EKS", link="#"),
            Project(title="Observability Stack", icon="bi-activity", position=3,
                    description=("Full Prometheus + Grafana + Loki monitoring stack with custom "
                                 "alerting and SLO dashboards."),
                    tags="Prometheus,Grafana,Loki", link="#"),
        ])

    db.session.commit()


def init_db():
    """Create tables if they don't exist yet and seed defaults."""
    with app.app_context():
        db.create_all()
        seed_defaults()


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5002)
