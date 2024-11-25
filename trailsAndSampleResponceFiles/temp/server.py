from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/status', methods=['GET'])
def status():
    """
    Endpoint to check the server status.
    """
    return jsonify({"status": "Server is running"}), 200

def start_server():
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
