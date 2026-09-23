from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
import os
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "legalconnect-secret-key")

def admin_required():
    if "user_id" not in session:
        return False
    if session.get("role") != "admin":
        return False
    return True


def provider_required():
    if "user_id" not in session:
        return False
    if session.get("role") != "provider":
        return False
    return True


def citizen_required():
    if "user_id" not in session:
        return False
    if session.get("role") != "citizen":
        return False
    return True
from urllib.parse import urlparse

def get_db_connection():

    database_url = os.getenv("MYSQL_PUBLIC_URL")

    if database_url:
        url = urlparse(database_url)

        connection = mysql.connector.connect(
            host=url.hostname,
            port=url.port,
            user=url.username,
            password=url.password,
            database=url.path.lstrip("/")
        )

    else:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "root"),
            database=os.getenv("DB_NAME", "legalconnect")
        )

    return connection
def get_db_connection():
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="legalconnect"
    )
    return connection


@app.route("/")
def home():
    connection = get_db_connection()
    connection.close()
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                (name, email, hashed_password, role)
            )
            connection.commit()
        finally:
            cursor.close()
            connection.close()

        return "Registration successful!"

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )
            user = cursor.fetchone()
        finally:
            cursor.close()
            connection.close()

        if user is None:
            return "Email not registered!"

        if not check_password_hash(user["password"], password):
            return "Incorrect password!"

        session["user_id"] = user["id"]
        session["role"] = user["role"]

        if user["role"] == "citizen":
            return redirect("/citizen-dashboard")
        elif user["role"] == "provider":
            return redirect("/provider-dashboard")
        elif user["role"] == "admin":
            return redirect("/admin-dashboard")
        else:
            return "Invalid user role!"

    return render_template("login.html")


@app.route("/citizen-dashboard")
def citizen_dashboard():
    if not citizen_required():
        return "Access denied!"
    return render_template("citizen_dashboard.html")


@app.route("/provider-dashboard")
def provider_dashboard():
    if not provider_required():
        return "Access denied!"

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                providers.*,
                users.name
            FROM providers
            JOIN users
            ON providers.user_id = users.id
            WHERE providers.user_id = %s
            """,
            (user_id,)
        )
        provider = cursor.fetchone()

        if provider is None:
            return "Provider profile not found!"

        cursor.execute(
            """
            SELECT COALESCE(SUM(points), 0) AS total_points
            FROM incentives
            WHERE provider_id = %s
            """,
            (provider["id"],)
        )
        result = cursor.fetchone()
        total_points = result["total_points"]
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "provider_dashboard.html",
        provider=provider,
        total_points=total_points
    )


@app.route("/provider-onboarding", methods=["GET", "POST"])
def provider_onboarding():
    if not provider_required():
        return "Access denied!"

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        if request.method == "POST":
            provider_type = request.form["provider_type"]
            specialization = request.form["specialization"]
            experience = request.form["experience"]
            location = request.form["location"]
            availability = request.form["availability"]

            cursor.execute(
                """
                UPDATE providers
                SET provider_type = %s,
                    specialization = %s,
                    experience = %s,
                    location = %s,
                    availability = %s
                WHERE user_id = %s
                """,
                (
                    provider_type,
                    specialization,
                    experience,
                    location,
                    availability,
                    user_id
                )
            )

            connection.commit()

            return "Provider profile saved successfully!"

    finally:
        cursor.close()
        connection.close()

    return render_template("provider_onboarding.html")


@app.route("/admin-dashboard")
def admin_dashboard():
    if session.get("role") != "admin":
        return "Access denied!"
    return render_template("admin_dashboard.html")


@app.route("/admin-providers")
def admin_providers():
    if session.get("role") != "admin":
        return "Access denied!"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM providers")
        providers = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "admin_providers.html",
        providers=providers
    )


@app.route("/verify-provider/<int:provider_id>", methods=["POST"])
def verify_provider(provider_id):
    if not admin_required():
        return "Access denied!"

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT verification_status
            FROM providers
            WHERE id = %s
            """,
            (provider_id,)
        )

        provider = cursor.fetchone()

        if provider is None:
            return "Provider not found!"

        if provider[0] == "Verified":
            return "Provider is already verified!"

        cursor.execute(
            """
            UPDATE providers
            SET verification_status = 'Verified'
            WHERE id = %s
            """,
            (provider_id,)
        )

        cursor.execute(
            """
            INSERT INTO incentives
            (provider_id, points, activity)
            VALUES (%s, %s, %s)
            """,
            (provider_id, 25, "Provider Verification")
        )

        connection.commit()

    finally:
        cursor.close()
        connection.close()

    return redirect("/admin-providers")


@app.route("/provider-incentives")
def provider_incentives():
    if not provider_required():
        return "Access denied!"

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT id FROM providers WHERE user_id = %s",
            (user_id,)
        )
        provider = cursor.fetchone()

        if provider is None:
            return "Provider profile not found!"

        provider_id = provider["id"]

        cursor.execute(
            """
            SELECT * FROM incentives
            WHERE provider_id = %s
            ORDER BY earned_at DESC
            """,
            (provider_id,)
        )
        incentives = cursor.fetchall()

        cursor.execute(
            """
            SELECT COALESCE(SUM(points), 0) AS total_points
            FROM incentives
            WHERE provider_id = %s
            """,
            (provider_id,)
        )
        result = cursor.fetchone()
        total_points = result["total_points"]
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "provider_incentives.html",
        incentives=incentives,
        total_points=total_points
    )


@app.route("/search-providers")
def search_providers():
    provider_type = request.args.get("provider_type")
    specialization = request.args.get("specialization")
    location = request.args.get("location")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            providers.*,
            users.name
        FROM providers
        JOIN users
        ON providers.user_id = users.id
        WHERE providers.verification_status = 'Verified'
    """

    values = []

    if provider_type:
        query += " AND providers.provider_type = %s"
        values.append(provider_type)

    if specialization:
        query += " AND providers.specialization LIKE %s"
        values.append("%" + specialization + "%")

    if location:
        query += " AND providers.location LIKE %s"
        values.append("%" + location + "%")

    try:
        cursor.execute(query, tuple(values))
        providers = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "search_providers.html",
        providers=providers
    )


@app.route("/request-service/<int:provider_id>", methods=["GET", "POST"])
def request_service(provider_id):
    if not citizen_required():
        return "Access denied!"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Get provider details
        cursor.execute(
            """
            SELECT
                providers.*,
                users.name
            FROM providers
            JOIN users
            ON providers.user_id = users.id
            WHERE providers.id = %s
            """,
            (provider_id,)
        )
        provider = cursor.fetchone()

        # Get available legal services
        cursor.execute(
            """
            SELECT * FROM services
            ORDER BY service_name
            """
        )
        services = cursor.fetchall()

        if request.method == "POST":
            service_id = request.form["service_id"]
            description = request.form["description"]
            user_id = session["user_id"]

            cursor.execute(
                "SELECT id FROM citizens WHERE user_id = %s",
                (user_id,)
            )
            citizen = cursor.fetchone()
            if not citizen:
                return "Citizen profile not found!"

            citizen_id = citizen["id"]

            cursor.execute(
                """
                INSERT INTO requests
                (citizen_id, provider_id, service_id, description)
                VALUES (%s, %s, %s, %s)
                """,
                (citizen_id, provider_id, service_id, description)
            )
            connection.commit()
            return "Service request submitted successfully!"
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "request_service.html",
        provider=provider,
        services=services
    )


@app.route("/provider-requests")
def provider_requests():
    if not provider_required():
        return "Access denied!"

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT id FROM providers WHERE user_id = %s",
            (user_id,)
        )
        provider = cursor.fetchone()

        if provider is None:
            return "Provider profile not found!"

        provider_id = provider["id"]

        cursor.execute(
            """
            SELECT
                requests.*,
                users.name AS citizen_name,
                services.service_name
            FROM requests
            JOIN citizens
            ON requests.citizen_id = citizens.id
            JOIN users
            ON citizens.user_id = users.id
            JOIN services
            ON requests.service_id = services.id
            WHERE requests.provider_id = %s
            ORDER BY requests.requested_at DESC
            """,
            (provider_id,)
        )
        requests = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "provider_requests.html",
        requests=requests
    )


@app.route("/update-request/<int:request_id>/<status>", methods=["POST"])
def update_request(request_id, status):
    if not provider_required():
        return "Access denied!"

    if status not in ["Accepted", "Rejected", "Completed"]:
        return "Invalid request status!"

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT id
            FROM providers
            WHERE user_id = %s
            """,
            (user_id,)
        )

        provider = cursor.fetchone()

        if provider is None:
            return "Provider profile not found!"

        provider_id = provider["id"]

        cursor.execute(
            """
            SELECT provider_id, status
            FROM requests
            WHERE id = %s
            AND provider_id = %s
            """,
            (request_id, provider_id)
        )

        request_data = cursor.fetchone()

        if request_data is None:
            return "Request not found or access denied!"

        old_status = request_data["status"]

        cursor.execute(
            """
            UPDATE requests
            SET status = %s
            WHERE id = %s
            AND provider_id = %s
            """,
            (status, request_id, provider_id)
        )

        if status == "Accepted" and old_status != "Accepted":
            cursor.execute(
                """
                INSERT INTO incentives
                (provider_id, points, activity)
                VALUES (%s, %s, %s)
                """,
                (provider_id, 5, "Accepted Service Request")
            )

        if status == "Completed" and old_status != "Completed":
            cursor.execute(
                """
                INSERT INTO incentives
                (provider_id, points, activity)
                VALUES (%s, %s, %s)
                """,
                (provider_id, 20, "Completed Service")
            )

        connection.commit()

    finally:
        cursor.close()
        connection.close()

    return redirect("/provider-requests")


@app.route("/ai-recommendations")
def ai_recommendations():
    if not citizen_required():
        return "Access denied!"

    service = request.args.get("service")
    location = request.args.get("location")

    providers = []

    if service and location:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                """
                SELECT
                    providers.*,
                    users.name
                FROM providers
                JOIN users
                ON providers.user_id = users.id
                WHERE providers.verification_status = 'Verified'
                AND providers.availability = 'Available'
                AND providers.location LIKE %s
                """,
                ("%" + location + "%",)
            )
            providers = cursor.fetchall()
        finally:
            cursor.close()
            connection.close()

        for provider in providers:
            score = 0

            if service == "Legal Consultation" and provider["provider_type"] == "Advocate":
                score += 40
            elif service == "Dispute Resolution" and provider["provider_type"] == "Arbitrator":
                score += 40
            elif service == "Mediation" and provider["provider_type"] == "Mediator":
                score += 40
            elif service == "Notary Services" and provider["provider_type"] == "Notary":
                score += 40
            elif service == "Document Preparation" and provider["provider_type"] == "Document Writer":
                score += 40

            score += min(provider["experience"] * 2, 30)
            score += min(float(provider["rating"]) * 5, 25)

            provider["match_score"] = round(score, 2)

        providers.sort(
            key=lambda x: x["match_score"],
            reverse=True
        )

    return render_template(
        "ai_recommendations.html",
        providers=providers
    )


@app.route("/citizen-requests")
def citizen_requests():
    if not citizen_required():
        return "Access denied!"

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT id FROM citizens WHERE user_id = %s",
            (user_id,)
        )
        citizen = cursor.fetchone()
        if not citizen:
            return "Citizen profile not found!"

        citizen_id = citizen["id"]

        cursor.execute(
            """
            SELECT
                requests.*,
                users.name AS provider_name,
                providers.provider_type,
                services.service_name
            FROM requests
            JOIN providers
            ON requests.provider_id = providers.id
            JOIN users
            ON providers.user_id = users.id
            JOIN services
            ON requests.service_id = services.id
            WHERE requests.citizen_id = %s
            ORDER BY requests.requested_at DESC
            """,
            (citizen_id,)
        )
        requests = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "citizen_requests.html",
        requests=requests
    )


@app.route("/rate-provider/<int:provider_id>", methods=["GET", "POST"])
def rate_provider(provider_id):
    if not citizen_required():
        return "Access denied!"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT providers.*, users.name
            FROM providers
            JOIN users ON providers.user_id = users.id
            WHERE providers.id = %s
            """,
            (provider_id,)
        )
        provider = cursor.fetchone()

        if request.method == "POST":
            rating = request.form["rating"]
            review = request.form["review"]
            user_id = session["user_id"]

            cursor.execute(
                "SELECT id FROM citizens WHERE user_id = %s",
                (user_id,)
            )
            citizen = cursor.fetchone()
            if not citizen:
                return "Citizen profile not found!"

            citizen_id = citizen["id"]

            cursor.execute(
                """
                INSERT INTO ratings
                (citizen_id, provider_id, rating, review)
                VALUES (%s, %s, %s, %s)
                """,
                (citizen_id, provider_id, rating, review)
            )

            cursor.execute(
                """
                SELECT AVG(rating) AS average_rating
                FROM ratings
                WHERE provider_id = %s
                """,
                (provider_id,)
            )
            result = cursor.fetchone()

            cursor.execute(
                """
                UPDATE providers
                SET rating = %s
                WHERE id = %s
                """,
                (result["average_rating"], provider_id)
            )

            connection.commit()
            return "Rating submitted successfully!"
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "rate_provider.html",
        provider=provider
    )


@app.route("/provider-profile")
def provider_profile():
    if not provider_required():
        return "Access denied!"

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                providers.*,
                users.name,
                users.email
            FROM providers
            JOIN users
            ON providers.user_id = users.id
            WHERE providers.user_id = %s
            """,
            (user_id,)
        )
        provider = cursor.fetchone()

        if provider is None:
            return "Provider profile not found!"
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "provider_profile.html",
        provider=provider
    )


@app.route("/upload-documents", methods=["GET", "POST"])
def upload_documents():
    if not provider_required():
        return "Access denied!"

    if request.method == "POST":
        document_name = request.form["document_name"]
        document_type = request.form["document_type"]

        file = request.files["document"]

        if file.filename == "":
            return "Please select a document!"

        filename = secure_filename(file.filename)
        file.save("uploads/" + filename)

        user_id = session["user_id"]

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO documents
                (user_id, document_name, document_type)
                VALUES (%s, %s, %s)
                """,
                (user_id, document_name, document_type)
            )
            connection.commit()
        finally:
            cursor.close()
            connection.close()

        return "Document uploaded successfully!"

    return render_template("upload_documents.html")


@app.route("/admin-documents")
def admin_documents():
    if session.get("role") != "admin":
        return "Access denied!"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                documents.*,
                users.name AS provider_name
            FROM documents
            JOIN users
            ON documents.user_id = users.id
            ORDER BY documents.uploaded_at DESC
            """
        )
        documents = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "admin_documents.html",
        documents=documents
    )


@app.route("/verify-document/<int:document_id>", methods=["POST"])
def verify_document(document_id):
    if not admin_required():
        return "Access denied!"

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE documents
            SET document_status = 'Verified'
            WHERE id = %s
            """,
            (document_id,)
        )

        connection.commit()

    finally:
        cursor.close()
        connection.close()

    return redirect("/admin-documents")


@app.route("/admin-reports")
def admin_reports():
    if session.get("role") != "admin":
        return "Access denied!"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT COUNT(*) AS total FROM users")
        total_users = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM providers")
        total_providers = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM providers
            WHERE verification_status = 'Verified'
            """
        )
        verified_providers = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM citizens")
        total_citizens = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM requests")
        total_requests = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM requests
            WHERE status = 'Completed'
            """
        )
        completed_requests = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT COALESCE(SUM(points), 0) AS total
            FROM incentives
            """
        )
        total_points = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM ratings")
        total_ratings = cursor.fetchone()["total"]
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "admin_reports.html",
        total_users=total_users,
        total_providers=total_providers,
        verified_providers=verified_providers,
        total_citizens=total_citizens,
        total_requests=total_requests,
        completed_requests=completed_requests,
        total_points=total_points,
        total_ratings=total_ratings
    )


@app.route("/admin-requests")
def admin_requests():
    if not admin_required():
        return "Access denied!"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                requests.*,
                citizens_user.name AS citizen_name,
                provider_user.name AS provider_name,
                services.service_name
            FROM requests

            JOIN citizens
            ON requests.citizen_id = citizens.id

            JOIN users AS citizens_user
            ON citizens.user_id = citizens_user.id

            JOIN providers
            ON requests.provider_id = providers.id

            JOIN users AS provider_user
            ON providers.user_id = provider_user.id

            JOIN services
            ON requests.service_id = services.id

            ORDER BY requests.requested_at DESC
            """
        )

        requests = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "admin_requests.html",
        requests=requests
    )


@app.route("/admin-users")
def admin_users():
    if not admin_required():
        return "Access denied!"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT *
            FROM users
            ORDER BY created_at DESC
            """
        )

        users = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    return render_template(
        "admin_users.html",
        users=users
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
    
if __name__ == "__main__":
    print(app.url_map)
    app.run(debug=True)