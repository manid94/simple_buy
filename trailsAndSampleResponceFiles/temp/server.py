

from flask import Flask, request, jsonify


__name__ = '__main__'
app = Flask(__name__)


@app.route('/status', methods=['GET'])
def status():
    """
    Endpoint to check the server status.
    """
    return jsonify({"status": "Server is running"}), 200

if __name__ == '__main__':
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)