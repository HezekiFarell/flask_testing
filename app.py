from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import json
from datetime import datetime
import random
import os

# Import model hanya jika file exists
try:
    from model import recommendation_model
    ML_AVAILABLE = True
except ImportError:
    print("Warning: ML model not available. Using fallback recommendations.")
    ML_AVAILABLE = False
    # Create a simple fallback
    class FallbackModel:
        def predict_recommendation(self, user_data):
            # Simple rule-based fallback
            score = user_data.get('skor_pretest', 0)
            if score < 40:
                return 'Pemula'
            elif score < 70:
                return 'Menengah'
            else:
                return 'Lanjutan'
        
        def load_model(self):
            return True
            
        def train_model(self):
            return True
    
    recommendation_model = FallbackModel()

app = Flask(__name__)
app.run(host='0.0.0.0', debug = True)

# Initialize database
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  email TEXT,
                  kelompok TEXT DEFAULT 'control',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Pre-test results
    c.execute('''CREATE TABLE IF NOT EXISTS pretest_results
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  answers TEXT NOT NULL,
                  score INTEGER NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    # Post-test results
    c.execute('''CREATE TABLE IF NOT EXISTS posttest_results
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  answers TEXT NOT NULL,
                  score INTEGER NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    # User profiles for ML - UPDATED structure
    c.execute('''CREATE TABLE IF NOT EXISTS user_profiles
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  usia INTEGER,
                  jenis_kelamin TEXT,
                  pendidikan TEXT,
                  pengalaman INTEGER,
                  minat_1 INTEGER,
                  minat_2 INTEGER,
                  minat_3 INTEGER,
                  minat_4 INTEGER,
                  minat_5 INTEGER,
                  lokasi TEXT,
                  skor_pretest INTEGER,
                  level_rekomendasi TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    conn.commit()
    conn.close()

# Database helper functions
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('home'))

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check profile completion
    conn = get_db_connection()
    profile = conn.execute('SELECT * FROM user_profiles WHERE user_id = ?', 
                          (session['user_id'],)).fetchone()
    pretest = conn.execute('SELECT * FROM pretest_results WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', 
                          (session['user_id'],)).fetchone()
    conn.close()
    
    profile_complete = profile is not None
    pretest_complete = pretest is not None
    
    # Update session flags
    session['profile_complete'] = profile_complete
    session['pretest_score'] = pretest['score'] if pretest else None
    session['education_accessed'] = session.get('education_accessed', False)
    
    return render_template('dashboard.html', 
                         username=session['username'], 
                         kelompok=session['kelompok'],
                         profile_complete=profile_complete,
                         pretest_complete=pretest_complete)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']  # In production, use proper hashing
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', 
                           (username, password)).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['kelompok'] = user['kelompok']
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah!', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        # Randomly assign to experimental or control group
        kelompok = 'experiment' if random.random() > 0.5 else 'control'
        
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO users (username, password, email, kelompok) VALUES (?, ?, ?, ?)',
                        (username, password, email, kelompok))
            conn.commit()
            conn.close()
            
            flash('Registrasi berhasil! Silakan login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username sudah digunakan!', 'error')
    
    return render_template('register.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Collect user profile data with defaults
            usia = request.form.get('usia', 25)
            jenis_kelamin = request.form.get('jenis_kelamin', 'L')
            pendidikan = request.form.get('pendidikan', 'SMA')
            lokasi = request.form.get('lokasi', 'Jakarta')
            pengalaman = request.form.get('pengalaman', 0)
            
            # Minat dengan nilai default
            minat_1 = request.form.get('minat_1', 3)
            minat_2 = request.form.get('minat_2', 3)  
            minat_3 = request.form.get('minat_3', 3)
            minat_4 = request.form.get('minat_4', 3)
            minat_5 = request.form.get('minat_5', 3)
            
            # Convert to integers
            usia = int(usia) if usia else 25
            pengalaman = int(pengalaman) if pengalaman else 0
            minat_1 = int(minat_1) if minat_1 else 3
            minat_2 = int(minat_2) if minat_2 else 3
            minat_3 = int(minat_3) if minat_3 else 3
            minat_4 = int(minat_4) if minat_4 else 3
            minat_5 = int(minat_5) if minat_5 else 3
            
            # Save to database
            conn = get_db_connection()
            
            # Check if profile exists
            existing_profile = conn.execute(
                'SELECT * FROM user_profiles WHERE user_id = ?', 
                (session['user_id'],)
            ).fetchone()
            
            if existing_profile:
                # Update existing profile - PERBAIKAN SINI
                conn.execute('''UPDATE user_profiles 
                             SET usia=?, jenis_kelamin=?, pendidikan=?, lokasi=?, pengalaman=?,
                             minat_1=?, minat_2=?, minat_3=?, minat_4=?, minat_5=?
                             WHERE user_id=?''',
                            (usia, jenis_kelamin, pendidikan, lokasi, pengalaman,
                             minat_1, minat_2, minat_3, minat_4, minat_5,
                             session['user_id']))
            else:
                # Insert new profile - PERBAIKAN SINI
                conn.execute('''INSERT INTO user_profiles 
                             (user_id, usia, jenis_kelamin, pendidikan, lokasi, pengalaman,
                             minat_1, minat_2, minat_3, minat_4, minat_5)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (session['user_id'], usia, jenis_kelamin, pendidikan, lokasi, pengalaman,
                             minat_1, minat_2, minat_3, minat_4, minat_5))
            
            conn.commit()
            conn.close()
            
            session['profile_complete'] = True
            flash('Profil berhasil disimpan!', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            flash(f'Error menyimpan profil: {str(e)}', 'error')
            print(f"Error in profile route: {e}")
            return redirect(url_for('profile'))
    
    # Check if profile already exists to pre-fill form
    conn = get_db_connection()
    profile_data = conn.execute('SELECT * FROM user_profiles WHERE user_id = ?', 
                          (session['user_id'],)).fetchone()
    conn.close()
    
    return render_template('profile.html', profile=profile_data)

@app.route('/pretest', methods=['GET', 'POST'])
def pretest():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Process pre-test answers
        answers = {}
        score = 0
        
        # Sample questions
        questions = ['q1', 'q2', 'q3', 'q4', 'q5']
        for q in questions:
            answer = request.form.get(q, '0')
            answers[q] = answer
            # Simple scoring
            if answer.isdigit():
                score += int(answer)
        
        # Save to database
        conn = get_db_connection()
        conn.execute('INSERT INTO pretest_results (user_id, answers, score) VALUES (?, ?, ?)',
                    (session['user_id'], json.dumps(answers), score))
        
        # Update user profile with pretest score
        conn.execute('UPDATE user_profiles SET skor_pretest = ? WHERE user_id = ?',
                    (score, session['user_id']))
        
        conn.commit()
        conn.close()
        
        session['pretest_score'] = score
        flash(f'Pre-test completed! Score: {score}', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('pretest.html')

@app.route('/education')
def education():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'pretest_score' not in session:
        return redirect(url_for('pretest'))
    
    # Get user profile
    conn = get_db_connection()
    profile = conn.execute('''SELECT up.*, pr.score as skor_pretest 
                            FROM user_profiles up 
                            JOIN pretest_results pr ON up.user_id = pr.user_id 
                            WHERE up.user_id = ? 
                            ORDER BY pr.created_at DESC LIMIT 1''', 
                          (session['user_id'],)).fetchone()
    conn.close()
    
    if not profile:
        flash('Silakan lengkapi profil terlebih dahulu', 'error')
        return redirect(url_for('profile'))
    
    # Mark that user has accessed education
    session['education_accessed'] = True
    
    # Convert sqlite3.Row to dictionary for easier access
    profile_dict = dict(profile) if profile else {}
    
    if session['kelompok'] == 'experiment' and ML_AVAILABLE:
        # Use ML model for experimental group with safe column access
        user_data = {
            'usia': profile_dict.get('usia', 25),
            'jenis_kelamin': profile_dict.get('jenis_kelamin', 'L'),
            'pendidikan': profile_dict.get('pendidikan', 'SMA'),
            'pengalaman': profile_dict.get('pengalaman', 0),
            'skor_pretest': profile_dict.get('skor_pretest', 0),
            'minat_1': profile_dict.get('minat_1', 3),
            'minat_2': profile_dict.get('minat_2', 3),
            'minat_3': profile_dict.get('minat_3', 3),
            'minat_4': profile_dict.get('minat_4', 3),
            'minat_5': profile_dict.get('minat_5', 3),
            'lokasi': profile_dict.get('lokasi', 'Jakarta')
        }
        
        # Get ML recommendation
        try:
            recommendation = recommendation_model.predict_recommendation(user_data)
            
            # Save recommendation to database
            conn = get_db_connection()
            conn.execute('UPDATE user_profiles SET level_rekomendasi = ? WHERE user_id = ?',
                        (recommendation, session['user_id']))
            conn.commit()
            conn.close()
            
            content = get_personalized_content(recommendation)
            template_name = 'education_experiment.html'
            
        except Exception as e:
            print(f"ML prediction failed: {e}")
            # Fallback to static content
            content = get_static_content()
            template_name = 'education_control.html'
            
    else:
        # Static content for control group or ML failure
        content = get_static_content()
        template_name = 'education_control.html'
    
    return render_template(template_name, content=content, kelompok=session['kelompok'])

def get_personalized_content(recommendation):
    """Get personalized content based on ML recommendation"""
    content_map = {
        'Pemula': {
            'title': 'Materi Level Pemula - Personalisasi',
            'level': 'Pemula',
            'content': [
                'Konsep dasar rehabilitasi medis dan pentingnya konsistensi dalam proses pemulihan.',
                'Teknik pernapasan dan relaksasi untuk mengurangi ketegangan otot dan meningkatkan sirkulasi darah.',
                'Latihan dasar penguatan otot dengan panduan visual yang mudah diikuti.',
                'Pentingnya nutrisi seimbang dan hidrasi yang cukup selama proses rehabilitasi.',
                'Strategi mengatasi hambatan mental dan membangun motivasi untuk konsistensi latihan.'
            ]
        },
        'Menengah': {
            'title': 'Materi Level Menengah - Personalisasi',
            'level': 'Menengah',
            'content': [
                'Teknik rehabilitasi tingkat menengah dengan fokus pada koordinasi dan keseimbangan.',
                'Latihan fungsional untuk aktivitas sehari-hari dengan intensitas yang disesuaikan.',
                'Manajemen nyeri dan strategi mengatasi ketidaknyamanan selama rehabilitasi.',
                'Peningkatan daya tahan tubuh melalui latihan progresif yang terukur.',
                'Integrasi teknologi dan alat bantu dalam proses rehabilitasi modern.'
            ]
        },
        'Lanjutan': {
            'title': 'Materi Level Lanjutan - Personalisasi',
            'level': 'Lanjutan',
            'content': [
                'Teknik rehabilitasi kompleks untuk kondisi spesifik dengan pendekatan multidisiplin.',
                'Program latihan intensif dengan monitoring perkembangan real-time.',
                'Strategi pemeliharaan hasil rehabilitasi dan pencegangan regresi.',
                'Integrasi mindfulness dan teknik mental dalam proses pemulihan fisik.',
                'Pengembangan rencana jangka panjang untuk kesehatan dan kebugaran berkelanjutan.'
            ]
        }
    }
    
    return content_map.get(recommendation, content_map['Pemula'])

def get_static_content():
    """Get static content for control group"""
    return {
        'title': 'Materi Edukasi Rehabilitasi Standar',
        'content': [
            'Pengenalan umum tentang rehabilitasi medis dan manfaatnya bagi pemulihan kesehatan.',
            'Prinsip dasar latihan fisik yang aman dan efektif untuk berbagai kondisi.',
            'Pentingnya konsistensi dan disiplin dalam menjalani program rehabilitasi.',
            'Tips mengatur jadwal latihan yang seimbang dengan aktivitas sehari-hari.',
            'Pemahaman tentang tanda-tanda kemajuan dan kapan harus berkonsultasi dengan profesional.'
        ]
    }

@app.route('/posttest', methods=['GET', 'POST'])
def posttest():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'pretest_score' not in session:
        return redirect(url_for('pretest'))
    
    if request.method == 'POST':
        # Process post-test answers
        answers = {}
        score = 0
        
        questions = ['q1', 'q2', 'q3', 'q4', 'q5']
        for q in questions:
            answer = request.form.get(q, '0')
            answers[q] = answer
            if answer.isdigit():
                score += int(answer)
        
        # Save to database
        conn = get_db_connection()
        conn.execute('INSERT INTO posttest_results (user_id, answers, score) VALUES (?, ?, ?)',
                    (session['user_id'], json.dumps(answers), score))
        conn.commit()
        conn.close()
        
        session['posttest_score'] = score
        flash(f'Post-test completed! Score: {score}', 'success')
        return redirect(url_for('results'))
    
    return render_template('posttest.html')

@app.route('/results')
def results():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'posttest_score' not in session:
        return redirect(url_for('posttest'))
    
    pretest_score = session.get('pretest_score', 0)
    posttest_score = session.get('posttest_score', 0)
    improvement = posttest_score - pretest_score
    
    return render_template('results.html', 
                         pretest_score=pretest_score,
                         posttest_score=posttest_score,
                         improvement=improvement,
                         kelompok=session['kelompok'])

@app.route('/admin/analysis')
def admin_analysis():
    # Simple admin analysis page
    conn = get_db_connection()
    
    # Get all results for analysis
    results = conn.execute('''SELECT u.kelompok, pr.score as pretest, ptr.score as posttest,
                             (ptr.score - pr.score) as improvement
                          FROM users u
                          JOIN pretest_results pr ON u.id = pr.user_id
                          JOIN posttest_results ptr ON u.id = ptr.user_id''').fetchall()
    
    # Get user profiles data for ML analysis
    profiles = conn.execute('''SELECT up.*, u.kelompok 
                            FROM user_profiles up
                            JOIN users u ON up.user_id = u.id
                            WHERE up.usia IS NOT NULL''').fetchall()
    
    conn.close()
    
    # Calculate statistics
    experiment_scores = [r['improvement'] for r in results if r['kelompok'] == 'experiment']
    control_scores = [r['improvement'] for r in results if r['kelompok'] == 'control']
    
    stats = {
        'experiment_count': len(experiment_scores),
        'control_count': len(control_scores),
        'experiment_avg_improvement': sum(experiment_scores) / len(experiment_scores) if experiment_scores else 0,
        'control_avg_improvement': sum(control_scores) / len(control_scores) if control_scores else 0,
        'total_users': len(profiles)
    }
    
    return render_template('admin_analysis.html', results=results, stats=stats, profiles=profiles, admin=True)

@app.route('/admin/train_model')
def admin_train_model():
    """Route untuk melatih model ML manual"""
    try:
        if not ML_AVAILABLE:
            flash('ML module not available', 'error')
            return redirect(url_for('admin_analysis'))
            
        # Try to get real data from database first
        real_data = recommendation_model.get_user_data_from_db()
        
        if real_data is not None and len(real_data) >= 5:  # Reduced minimum samples
            # Use real data if we have enough samples
            print(f"Training with {len(real_data)} real user samples")
            success = recommendation_model.train_model(real_data)
        else:
            # Use generated data
            print("Not enough real data, using generated samples")
            success = recommendation_model.train_model()
        
        if success:
            flash('Model ML berhasil dilatih!', 'success')
        else:
            flash('Gagal melatih model ML', 'error')
        
    except Exception as e:
        flash(f'Error training model: {str(e)}', 'error')
    
    return redirect(url_for('admin_analysis'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    
    # Train model on startup if not exists
    if ML_AVAILABLE and not recommendation_model.load_model():
        print("Training recommendation model...")
        recommendation_model.train_model()
    
    app.run(debug=True)