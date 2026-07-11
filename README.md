# Smart Grid Enterprise Project

Detailed scaffold for internship project.

## How to Run

### Locally (with Python)
1. Activate virtual environment:
   - Windows: `.venv\Scripts\activate`
   - Unix/macOS: `source .venv/bin/activate`
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `uvicorn app.main:app --reload`
4. Open http://localhost:8000 in your browser.

### With Docker
1. Start services: `docker-compose up --build`
2. Open http://localhost:8000 in your browser.
