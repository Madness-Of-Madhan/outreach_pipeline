from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import json
import queue
import threading
import os
import sys

sys.path.append(os.path.dirname(__file__))
from pipeline import run_pipeline

app = Flask(__name__, static_folder="../frontend")
CORS(app)

# serve the frontend
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# this endpoint streams logs back to the browser as they happen
# using server-sent events (SSE) - found this approach on stackoverflow
@app.route("/run", methods=["GET"])
def run():
    seed = request.args.get("domain", "").strip()

    if not seed:
        return jsonify({"error": "domain is required"}), 400

    # clean up domain - remove https:// if someone pastes a full url
    seed = seed.replace("https://", "").replace("http://", "").rstrip("/")

    def generate():
        log_queue = queue.Queue()
        result_box = {}

        def log_fn(msg):
            log_queue.put({"type": "log", "message": msg})

        def worker():
            try:
                result = run_pipeline(seed, log_fn=log_fn)
                result_box["data"] = result
            except Exception as e:
                result_box["data"] = {"error": str(e)}
            finally:
                log_queue.put({"type": "done"})

        t = threading.Thread(target=worker)
        t.start()

        while True:
            try:
                item = log_queue.get(timeout=120)
                if item["type"] == "done":
                    # send final result
                    final = result_box.get("data", {})
                    yield f"data: {json.dumps({'type': 'result', 'data': final})}\n\n"
                    break
                else:
                    yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                # keep connection alive
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

        t.join()

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    print("starting server on http://localhost:5000")
    app.run(debug=True, threaded=True)
