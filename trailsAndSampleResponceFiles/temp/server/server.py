from flask import Flask, render_template, request, abort
import os

app = Flask(__name__)

# Base directory to explore
BASE_DIR = os.getcwd()

# Register a custom Jinja2 filter for dirname
@app.template_filter('dirname')
def dirname(path):
    return os.path.dirname(path)

# Register a custom Jinja2 filter for isdir
@app.template_filter('isdir')
def isdir(path):
    return os.path.isdir(path)


@app.route('/')
@app.route('/browse', methods=['GET'])
def browse():
    """
    List files and directories in the current path.
    """
    # Get the requested path or default to BASE_DIR
    requested_path = request.args.get('path', BASE_DIR)
    abs_path = os.path.abspath(requested_path)

    # Ensure path is within the BASE_DIR
    if not abs_path.startswith(BASE_DIR):
        return abort(403, "Access denied")

    try:
        # List directories and files
        items = os.listdir(abs_path)
        items = sorted(items, key=lambda x: os.path.isdir(os.path.join(abs_path, x)), reverse=True)  # Directories first
        return render_template('directory_list.html', items=items, current_path=abs_path, base_dir=BASE_DIR)
    except Exception as e:
        return f"Error accessing directory: {e}", 500

@app.route('/view-file', methods=['GET'])
def view_file():
    """
    View the content of a file.
    """
    file_path = request.args.get('file')
    abs_path = os.path.abspath(file_path)

    # Ensure file is within the BASE_DIR
    if not abs_path.startswith(BASE_DIR):
        return abort(403, "Access denied")

    if not os.path.isfile(abs_path):
        return abort(404, "File not found")

    try:
        with open(abs_path, 'r') as file:
            content = file.read()
        return render_template('file_content.html', file_name=os.path.basename(abs_path), content=content)
    except Exception as e:
        return f"Error reading file: {e}", 500



@app.route('/test')
def test():
    return "Welcome to the home page!"


def start_server():
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
