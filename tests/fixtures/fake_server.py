"""Minimal Flask fake corporate system for E2E testing."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, session, send_file, redirect, url_for


def create_app():
    app = Flask(__name__)
    app.secret_key = "test-secret"

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            session["user"] = request.form.get("user_id", "anon")
            return redirect("/")
        return """
<form method=post>
  <input name=user_id id=login_id>
  <input name=user_pw id=login_pw type=password>
  <button id=login_submit type=submit>Login</button>
</form>
"""

    @app.route("/")
    def home():
        if "user" not in session:
            return redirect("/login")
        return """
<a id='nav-stats' href='/stats'>통계</a>
<a id='nav-settings' href='/settings'>설정</a>
"""

    @app.route("/stats")
    def stats():
        if "user" not in session:
            return redirect("/login")
        return """
<button id='export-excel' data-test='export-excel' onclick="location='/download'">엑셀 다운로드</button>
"""

    @app.route("/download")
    def download():
        if "user" not in session:
            return redirect("/login")
        buf = io.BytesIO()
        pd.DataFrame({"날짜": ["2026-04-24"], "매출": [1234], "건수": [42]}).to_excel(buf, index=False)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="report.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return app


if __name__ == "__main__":
    create_app().run(port=0)
