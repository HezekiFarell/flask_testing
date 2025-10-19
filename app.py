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
    print("✅ ML model loaded successfully")
except ImportError as e:
    print(f"⚠️ ML model not available: {e}. Using fallback recommendations.")
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
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration
def get_db_connection():
    """Get database connection - supports both SQLite and PostgreSQL"""
    try:
        # Default to SQLite
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

# Initialize database
def init_db():
    """Initialize database tables"""
    try:
        conn = get_db_connection()
        if conn is None:
            print("❌ Cannot initialize database - no connection")
            return
            
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
        
        # User profiles for ML
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
        print("✅ Database tables initialized successfully")
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

@app.route('/')
def index():
    """Redirect to home page"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('home'))

@app.route('/home')
def home():
    """Home page"""
    return render_template('home.html')

@app.route('/dashboard')
def dashboard():
    """User dashboard"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu', 'error')
        return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Database error', 'error')
            return render_template('dashboard.html', 
                                 username=session.get('username'), 
                                 kelompok=session.get('kelompok', 'control'),
                                 profile_complete=False,
                                 pretest_complete=False)
        
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
        
        return render_template('dashboard.html', 
                             username=session['username'], 
                             kelompok=session['kelompok'],
                             profile_complete=profile_complete,
                             pretest_complete=pretest_complete)
                             
    except Exception as e:
        print(f"Dashboard error: {e}")
        return render_template('dashboard.html', 
                             username=session.get('username'), 
                             kelompok=session.get('kelompok', 'control'),
                             profile_complete=False,
                             pretest_complete=False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Username dan password harus diisi', 'error')
            return render_template('login.html')
        
        try:
            conn = get_db_connection()
            if conn is None:
                flash('Database error', 'error')
                return render_template('login.html')
                
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
                
        except Exception as e:
            print(f"Login error: {e}")
            flash('Terjadi error saat login', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        
        if not username or not password:
            flash('Username dan password harus diisi', 'error')
            return render_template('register.html')
        
        # Randomly assign to experimental or control group
        kelompok = 'experiment' if random.random() > 0.5 else 'control'
        
        try:
            conn = get_db_connection()
            if conn is None:
                flash('Database error', 'error')
                return render_template('register.html')
                
            conn.execute('INSERT INTO users (username, password, email, kelompok) VALUES (?, ?, ?, ?)',
                        (username, password, email, kelompok))
            conn.commit()
            conn.close()
            
            flash('Registrasi berhasil! Silakan login.', 'success')
            return redirect(url_for('login'))
            
        except sqlite3.IntegrityError:
            flash('Username sudah digunakan!', 'error')
        except Exception as e:
            print(f"Registration error: {e}")
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('register.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """User profile management"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Collect user profile data with defaults
            usia = request.form.get('usia', '25')
            jenis_kelamin = request.form.get('jenis_kelamin', 'L')
            pendidikan = request.form.get('pendidikan', 'SMA')
            lokasi = request.form.get('lokasi', 'Jakarta')
            pengalaman = request.form.get('pengalaman', '0')
            
            # Minat dengan nilai default
            minat_1 = request.form.get('minat_1', '3')
            minat_2 = request.form.get('minat_2', '3')  
            minat_3 = request.form.get('minat_3', '3')
            minat_4 = request.form.get('minat_4', '3')
            minat_5 = request.form.get('minat_5', '3')
            
            # Convert to integers dengan error handling
            try:
                usia = int(usia) if usia else 25
                pengalaman = int(pengalaman) if pengalaman else 0
                minat_1 = int(minat_1) if minat_1 else 3
                minat_2 = int(minat_2) if minat_2 else 3
                minat_3 = int(minat_3) if minat_3 else 3
                minat_4 = int(minat_4) if minat_4 else 3
                minat_5 = int(minat_5) if minat_5 else 3
            except ValueError:
                flash('Format input tidak valid', 'error')
                return redirect(url_for('profile'))
            
            # Save to database
            conn = get_db_connection()
            if conn is None:
                flash('Database error', 'error')
                return redirect(url_for('profile'))
            
            # Check if profile exists
            existing_profile = conn.execute(
                'SELECT * FROM user_profiles WHERE user_id = ?', 
                (session['user_id'],)
            ).fetchone()
            
            if existing_profile:
                # Update existing profile
                conn.execute('''UPDATE user_profiles 
                             SET usia=?, jenis_kelamin=?, pendidikan=?, lokasi=?, pengalaman=?,
                             minat_1=?, minat_2=?, minat_3=?, minat_4=?, minat_5=?
                             WHERE user_id=?''',
                            (usia, jenis_kelamin, pendidikan, lokasi, pengalaman,
                             minat_1, minat_2, minat_3, minat_4, minat_5,
                             session['user_id']))
            else:
                # Insert new profile
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
            print(f"Profile save error: {e}")
            flash(f'Error menyimpan profil: {str(e)}', 'error')
    
    # GET request - show profile form
    try:
        conn = get_db_connection()
        profile_data = None
        if conn:
            profile_data = conn.execute('SELECT * FROM user_profiles WHERE user_id = ?', 
                                  (session['user_id'],)).fetchone()
            conn.close()
        
        return render_template('profile.html', profile=profile_data)
        
    except Exception as e:
        print(f"Profile load error: {e}")
        return render_template('profile.html', profile=None)

@app.route('/pretest', methods=['GET', 'POST'])
def pretest():
    """Pre-test assessment"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
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
            if conn is None:
                flash('Database error', 'error')
                return redirect(url_for('pretest'))
                
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
            
        except Exception as e:
            print(f"Pretest error: {e}")
            flash('Error menyimpan hasil pre-test', 'error')
    
    return render_template('pretest.html')

@app.route('/education')
def education():
    """Education content - A/B testing implementation"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu', 'error')
        return redirect(url_for('login'))
    
    if not session.get('pretest_score'):
        flash('Silakan selesaikan pre-test terlebih dahulu', 'error')
        return redirect(url_for('pretest'))
    
    try:
        # Get user profile
        conn = get_db_connection()
        if conn is None:
            flash('Database error', 'error')
            return redirect(url_for('dashboard'))
            
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
        
        # Convert to dictionary for easier access
        profile_dict = dict(profile) if profile else {}
        
        # Determine content based on group and ML availability
        if session['kelompok'] == 'experiment' and ML_AVAILABLE:
            # Use ML model for experimental group
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
                if conn:
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
        
    except Exception as e:
        print(f"Education error: {e}")
        flash('Error mengakses materi edukasi', 'error')
        return redirect(url_for('dashboard'))

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
    """Post-test assessment"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu', 'error')
        return redirect(url_for('login'))
    
    if not session.get('pretest_score'):
        flash('Silakan selesaikan pre-test terlebih dahulu', 'error')
        return redirect(url_for('pretest'))
    
    if request.method == 'POST':
        try:
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
            if conn is None:
                flash('Database error', 'error')
                return redirect(url_for('posttest'))
                
            conn.execute('INSERT INTO posttest_results (user_id, answers, score) VALUES (?, ?, ?)',
                        (session['user_id'], json.dumps(answers), score))
            conn.commit()
            conn.close()
            
            session['posttest_score'] = score
            flash(f'Post-test completed! Score: {score}', 'success')
            return redirect(url_for('results'))
            
        except Exception as e:
            print(f"Posttest error: {e}")
            flash('Error menyimpan hasil post-test', 'error')
    
    return render_template('posttest.html')

@app.route('/results')
def results():
    """Show test results"""
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu', 'error')
        return redirect(url_for('login'))
    
    if not session.get('posttest_score'):
        flash('Silakan selesaikan post-test terlebih dahulu', 'error')
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
    """Admin analysis page"""
    try:
        conn = get_db_connection()
        if conn is None:
            return render_template('admin_analysis.html', 
                                 results=[], 
                                 stats={}, 
                                 profiles=[],
                                 admin=True)
        
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
        
    except Exception as e:
        print(f"Admin analysis error: {e}")
        return render_template('admin_analysis.html', 
                             results=[], 
                             stats={}, 
                             profiles=[],
                             admin=True)

@app.route('/admin/train_model')
def admin_train_model():
    """Manual ML model training"""
    try:
        if not ML_AVAILABLE:
            flash('ML module not available', 'error')
            return redirect(url_for('admin_analysis'))
            
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
    """User logout"""
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

@app.route('/health')
def health_check():
    """Health check endpoint for deployment"""
    return jsonify({
        'status': 'healthy', 
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'flask-ab-testing'
    })

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# Production setup
if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Train model on startup if available
    if ML_AVAILABLE:
        try:
            if not recommendation_model.load_model():
                print("Training recommendation model...")
                recommendation_model.train_model()
        except Exception as e:
            print(f"Model training error: {e}")
    
    # Production vs Development
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    
    print(f"🚀 Starting Flask A/B Testing App...")
    print(f"📊 ML Available: {ML_AVAILABLE}")
    print(f"🔧 Debug Mode: {debug_mode}")
    print(f"🌐 Port: {port}")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)