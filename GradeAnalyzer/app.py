import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from grade_processor import GradeProcessor

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_development")

# Configuration
UPLOAD_FOLDER = 'uploads'
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Main page with file upload form."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and process grades."""
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            flash('No file selected. Please choose a PDF file to upload.', 'error')
            return redirect(url_for('index'))
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            flash('No file selected. Please choose a PDF file to upload.', 'error')
            return redirect(url_for('index'))
        
        # Check file type
        if not allowed_file(file.filename):
            flash('Invalid file type. Please upload a PDF file only.', 'error')
            return redirect(url_for('index'))
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Process the PDF
        processor = GradeProcessor()
        try:
            results = processor.process_pdf(filepath)
            
            # Store results in session for display
            session['results'] = results
            session['filename'] = filename
            
            # Clean up uploaded file
            try:
                os.remove(filepath)
            except OSError:
                logging.warning(f"Could not remove uploaded file: {filepath}")
            
            return redirect(url_for('results'))
            
        except Exception as e:
            # Clean up uploaded file on error
            try:
                os.remove(filepath)
            except OSError:
                pass
            
            logging.error(f"Error processing PDF: {str(e)}")
            flash(f'Error processing PDF: {str(e)}', 'error')
            return redirect(url_for('index'))
    
    except RequestEntityTooLarge:
        flash('File too large. Please upload a PDF file smaller than 16MB.', 'error')
        return redirect(url_for('index'))
    
    except Exception as e:
        logging.error(f"Unexpected error during upload: {str(e)}")
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/results')
def results():
    """Display processing results."""
    if 'results' not in session:
        flash('No results to display. Please upload a PDF file first.', 'warning')
        return redirect(url_for('index'))
    
    results = session['results']
    filename = session.get('filename', 'Unknown file')
    
    return render_template('results.html', results=results, filename=filename)

@app.route('/clear')
def clear_results():
    """Clear session results and return to main page."""
    session.pop('results', None)
    session.pop('filename', None)
    flash('Results cleared. You can upload a new PDF file.', 'info')
    return redirect(url_for('index'))

@app.errorhandler(413)
def too_large(e):
    """Handle file too large error."""
    flash('File too large. Please upload a PDF file smaller than 16MB.', 'error')
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(e):
    """Handle internal server errors."""
    logging.error(f"Internal server error: {str(e)}")
    flash('An internal error occurred. Please try again.', 'error')
    return redirect(url_for('index'))
