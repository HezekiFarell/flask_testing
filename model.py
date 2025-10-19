import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import pickle
import sqlite3
import os

class RecommendationModel:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.model_path = 'recommendation_model.pkl'
        self.scaler_path = 'scaler.pkl'
        self.encoders_path = 'label_encoders.pkl'
        
    def generate_sample_data(self, n_samples=500):
        """Generate sample data for training when real data is not available"""
        np.random.seed(42)
        
        data = {
            'usia': np.random.randint(18, 65, n_samples),
            'jenis_kelamin': np.random.choice(['L', 'P'], n_samples),
            'lokasi': np.random.choice(['Jakarta', 'Bandung', 'Surabaya', 'Medan', 'Makassar'], n_samples),
            'pendidikan': np.random.choice(['SMA', 'D3', 'S1', 'S2', 'S3'], n_samples),
            'pengalaman': np.random.randint(0, 20, n_samples),
            'skor_pretest': np.random.randint(0, 101, n_samples),
            'minat_1': np.random.randint(1, 6, n_samples),
            'minat_2': np.random.randint(1, 6, n_samples),
            'minat_3': np.random.randint(1, 6, n_samples),
            'minat_4': np.random.randint(1, 6, n_samples),
            'minat_5': np.random.randint(1, 6, n_samples),
        }
        
        df = pd.DataFrame(data)
        
        # Generate target variable (level_rekomendasi) based on rules
        def determine_level(row):
            score = 0
            
            # Berdasarkan usia
            if row['usia'] < 25:
                score += 1
            elif row['usia'] < 40:
                score += 2
            else:
                score += 3
                
            # Berdasarkan skor pretest
            if row['skor_pretest'] < 40:
                score += 1
            elif row['skor_pretest'] < 70:
                score += 2
            else:
                score += 3
                
            # Berdasarkan pengalaman
            if row['pengalaman'] < 5:
                score += 1
            elif row['pengalaman'] < 10:
                score += 2
            else:
                score += 3
                
            # Berdasarkan minat rata-rata
            avg_interest = (row['minat_1'] + row['minat_2'] + row['minat_3'] + row['minat_4'] + row['minat_5']) / 5
            if avg_interest < 2.5:
                score += 1
            elif avg_interest < 4:
                score += 2
            else:
                score += 3
                
            # Determine level based on total score
            if score <= 6:
                return 'Pemula'
            elif score <= 9:
                return 'Menengah'
            else:
                return 'Lanjutan'
        
        df['level_rekomendasi'] = df.apply(determine_level, axis=1)
        
        return df
    
    def preprocess_data(self, df):
        """Preprocess the data for training"""
        df_processed = df.copy()
        
        # Encode categorical variables
        categorical_columns = ['jenis_kelamin', 'lokasi', 'pendidikan']
        
        for col in categorical_columns:
            if col not in self.label_encoders:
                self.label_encoders[col] = LabelEncoder()
            df_processed[col] = self.label_encoders[col].fit_transform(df_processed[col].astype(str))
        
        # Separate features and target
        X = df_processed.drop('level_rekomendasi', axis=1)
        y = df_processed['level_rekomendasi']
        
        # Scale numerical features
        numerical_columns = ['usia', 'pengalaman', 'skor_pretest', 'minat_1', 'minat_2', 'minat_3', 'minat_4', 'minat_5']
        X[numerical_columns] = self.scaler.fit_transform(X[numerical_columns])
        
        return X, y
    
    def train_model(self, df=None):
        """Train the recommendation model"""
        try:
            # Use provided data or generate sample data
            if df is None:
                print("Generating sample data for training...")
                df = self.generate_sample_data(100)  # Reduced sample size for faster training
            
            print(f"Training model with {len(df)} samples...")
            
            # Preprocess data
            X, y = self.preprocess_data(df)
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Train model with simpler parameters for reliability
            self.model = RandomForestClassifier(
                n_estimators=50,  # Reduced for faster training
                max_depth=8,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42
            )
            
            self.model.fit(X_train, y_train)
            
            # Evaluate model
            y_pred = self.model.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)
            print(f"Model trained with accuracy: {accuracy:.2f}")
            
            # Save model and preprocessing objects
            self.save_model()
            
            return True
            
        except Exception as e:
            print(f"Error training model: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def predict_recommendation(self, user_data):
        """Predict recommendation for a user"""
        try:
            if self.model is None:
                if not self.load_model():
                    print("Model not available, returning default recommendation")
                    return 'Pemula'
            
            # Create DataFrame from user data
            user_df = pd.DataFrame([user_data])
            
            # Preprocess user data
            categorical_columns = ['jenis_kelamin', 'lokasi', 'pendidikan']
            
            for col in categorical_columns:
                if col in user_df.columns and col in self.label_encoders:
                    # Handle unseen categories
                    if user_df[col].iloc[0] in self.label_encoders[col].classes_:
                        user_df[col] = self.label_encoders[col].transform([user_df[col].iloc[0]])[0]
                    else:
                        # Use default value for unseen labels
                        user_df[col] = 0
            
            # Ensure all required columns are present
            required_columns = ['usia', 'jenis_kelamin', 'lokasi', 'pendidikan', 'pengalaman', 
                              'skor_pretest', 'minat_1', 'minat_2', 'minat_3', 'minat_4', 'minat_5']
            
            for col in required_columns:
                if col not in user_df.columns:
                    if col in ['minat_4', 'minat_5', 'lokasi']:
                        # Set default values for optional columns
                        if col.startswith('minat'):
                            user_df[col] = 3
                        elif col == 'lokasi':
                            user_df[col] = 'Jakarta'
                    else:
                        user_df[col] = 0
            
            # Scale numerical features
            numerical_columns = ['usia', 'pengalaman', 'skor_pretest', 'minat_1', 'minat_2', 'minat_3', 'minat_4', 'minat_5']
            user_df[numerical_columns] = self.scaler.transform(user_df[numerical_columns])
            
            # Make prediction
            prediction = self.model.predict(user_df)[0]
            probability = np.max(self.model.predict_proba(user_df))
            
            print(f"Prediction: {prediction} (confidence: {probability:.2f})")
            
            return prediction
            
        except Exception as e:
            print(f"Error making prediction: {str(e)}")
            import traceback
            traceback.print_exc()
            return 'Pemula'  # Default fallback
    
    def save_model(self):
        """Save the trained model and preprocessing objects"""
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump(self.model, f)
            
            with open(self.scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            
            with open(self.encoders_path, 'wb') as f:
                pickle.dump(self.label_encoders, f)
            
            print("Model saved successfully")
            return True
            
        except Exception as e:
            print(f"Error saving model: {str(e)}")
            return False
    
    def load_model(self):
        """Load the trained model and preprocessing objects"""
        try:
            if not os.path.exists(self.model_path):
                print("Model file not found")
                return False
            
            with open(self.model_path, 'rb') as f:
                self.model = pickle.load(f)
            
            with open(self.scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)
            
            with open(self.encoders_path, 'rb') as f:
                self.label_encoders = pickle.load(f)
            
            print("Model loaded successfully")
            return True
            
        except Exception as e:
            print(f"Error loading model: {str(e)}")
            return False
    
    def get_user_data_from_db(self):
        """Get user data from database for training"""
        try:
            conn = sqlite3.connect('database.db')
            
            # Query to get user profiles with pretest scores
            query = '''
            SELECT 
                up.usia, 
                up.jenis_kelamin, 
                up.lokasi,
                up.pendidikan,
                up.pengalaman,
                pr.score as skor_pretest,
                up.minat_1,
                up.minat_2, 
                up.minat_3,
                up.minat_4,
                up.minat_5,
                up.level_rekomendasi
            FROM user_profiles up
            JOIN pretest_results pr ON up.user_id = pr.user_id
            WHERE up.level_rekomendasi IS NOT NULL
            '''
            
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            return df if not df.empty else None
            
        except Exception as e:
            print(f"Error getting data from database: {str(e)}")
            return None

# Global instance
recommendation_model = RecommendationModel()