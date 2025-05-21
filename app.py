from flask import Flask, request, render_template_string, send_file, session, redirect, url_for
from flask_session import Session
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import io
import pandas as pd
from weasyprint import HTML
import certifi
import logging
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'securekey'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LOGIN_PAGE = """
<!doctype html>
<title>Login</title>
<h2>Login</h2>
<form method="post">
  Username: <input name="username"><br>
  Password: <input name="password" type="password"><br>
  <input type="submit" value="Login">
</form>
"""

MAIN_TEMPLATE = """
<!doctype html>
<title>Website Media Auditor</title>
<h2>Website Media Auditor</h2>
<form method="POST">
  URL: <input name="url" type="url" required style="width: 300px" />
  <button type="submit">Scan</button>
</form>
{% if results %}
  <h3>Results ({{ results|length }} media files found)</h3>
  <table border="1" cellpadding="5">
    <tr><th>Preview</th><th>Type</th><th>Media URL</th><th>Page URL</th></tr>
    {% for r in results %}
      <tr>
        <td>{% if r['type'] == 'image' %}<img src="{{ r['media_url'] }}" width="100">{% else %}N/A{% endif %}</td>
        <td>{{ r['type'] }}</td>
        <td><a href="{{ r['media_url'] }}" target="_blank">View</a></td>
        <td><a href="{{ r['page_url'] }}" target="_blank">Source Page</a></td>
      </tr>
    {% endfor %}
  </table>
  <br>
  <a href="/export/csv">Download CSV</a> |
  <a href="/export/pdf">Download PDF</a>
{% endif %}
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'nrivera' and request.form['password'] == 'Temporary!!!':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return LOGIN_PAGE + "<p>Invalid credentials</p>"
    return LOGIN_PAGE

@app.route('/', methods=['GET', 'POST'])
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    results = []
    if request.method == 'POST':
        url = request.form.get('url')
        if url and is_valid_url(url):
            results = crawl_website(url)
            session['results'] = results
    else:
        results = session.get('results', [])
    return render_template_string(MAIN_TEMPLATE, results=results)

@app.route('/export/csv')
def export_csv():
    results = session.get('results', [])
    df = pd.DataFrame(results)
    csv_io = io.StringIO()
    df.to_csv(csv_io, index=False)
    csv_io.seek(0)
    return send_file(io.BytesIO(csv_io.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='media_audit.csv')

@app.route('/export/pdf')
def export_pdf():
    results = session.get('results', [])
    html_content = "<h1>Media Audit Report</h1><table border='1' cellpadding='5'><tr><th>Type</th><th>Media URL</th><th>Page URL</th></tr>"
    for item in results:
        html_content += f"<tr><td>{item['type']}</td><td>{item['media_url']}</td><td>{item['page_url']}</td></tr>"
    html_content += "</table>"
    pdf_io = io.BytesIO()
    HTML(string=html_content).write_pdf(pdf_io)
    pdf_io.seek(0)
    return send_file(pdf_io, mimetype='application/pdf', as_attachment=True, download_name='media_audit.pdf')

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme in ('http', 'https'), result.netloc])
    except Exception as e:
        logger.error(f"URL validation failed: {e}")
        return False

def extract_media(url, base, media_data):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10, verify=certifi.where())
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.content, 'html.parser')
        media_tags = [('img', 'src', 'image'), ('video', 'src', 'video'), ('audio', 'src', 'audio'), ('source', 'src', 'media')]
        for tag, attr, media_type in media_tags:
            for element in soup.find_all(tag):
                src = element.get(attr)
                if src:
                    full_url = urljoin(base, src)
                    media_data.append({'media_url': full_url, 'type': media_type, 'page_url': url})
        return [urljoin(base, a.get('href')) for a in soup.find_all('a', href=True)]
    except Exception as e:
        logger.error(f"Error extracting from {url}: {e}")
        return []

def crawl_website(start_url):
    visited_urls = set()
    media_data = []
    queue = [start_url]
    while queue:
        current_url = queue.pop(0)
        if current_url in visited_urls or not is_valid_url(current_url):
            continue
        visited_urls.add(current_url)
        links = extract_media(current_url, start_url, media_data)
        for link in links:
            if urlparse(link).netloc == urlparse(start_url).netloc and link not in visited_urls:
                queue.append(link)
        time.sleep(1)  # ← this slows it down just enough to prevent crashing
    return media_data

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
