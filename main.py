import os

from flask import Flask, render_template

app = Flask(__name__)


def backend_url():
    return os.getenv("BACKEND_URL", "").strip().rstrip("/")


@app.get("/")
def home():
    return render_template("index.html", backend_url=backend_url())


@app.get("/settings")
def settings():
    return render_template("settings.html", backend_url=backend_url())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
