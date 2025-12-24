# app.py - AI Interview System with Supabase and OpenAI
import streamlit as st
import os
from datetime import datetime
import json
from supabase import create_client, Client
from supabase.client import ClientOptions
from gtts import gTTS
import speech_recognition as sr
import tempfile
from openai import OpenAI
import PyPDF2
import io
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AI Interview System",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(120deg, #1f77b4, #ff7f0e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
        margin-bottom: 2rem;
    }
    .question-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        font-size: 1.3rem;
        margin: 2rem 0;
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
    }
    .score-card {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
    }
    .stButton>button {
        border-radius: 10px;
        height: 3rem;
        font-weight: bold;
        font-size: 1.1rem;
    }
    .answer-box {
        background-color: #f8f9fa;
        border-left: 4px solid #667eea;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .info-card {
        background-color: #e7f3ff;
        border-left: 4px solid #2196F3;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Database connection
@st.cache_resource
def get_db_connection():
    """Create PostgreSQL connection"""
    try:
        # Parse the connection string
        # postgresql://postgres:[YOUR-PASSWORD]@db.oiggghgcfckhvkpdytvq.supabase.co:5432/postgres
        db_url = os.getenv("DATABASE_URL", "postgresql://postgres:YOUR-PASSWORD@db.oiggghgcfckhvkpdytvq.supabase.co:5432/postgres")
        
        # For security, you can also set individual params
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "YOUR-PASSWORD"),
            host=os.getenv("DB_HOST", "db.oiggghgcfckhvkpdytvq.supabase.co"),
            port=os.getenv("DB_PORT", "5432")
        )
        return conn
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        return None
@st.cache_resource
def init_supabase() -> Client | None:
    """Initialize Supabase client safely"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # backend only

    if not url or not key:
        st.error("⚠️ Supabase credentials not configured. Check your .env file.")
        return None

    try:
        return create_client(
            url,
            key,
            options=ClientOptions(
                postgrest_client_timeout=30,
                storage_client_timeout=30,
            )
        )
    except Exception as e:
        st.error(f"Supabase init failed: {e}")
        return None

# Initialize OpenAI
@st.cache_resource
def init_openai():
    """Initialize OpenAI client"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        st.error("⚠️ OpenAI API key not configured. Please check your .env file.")
        return None
    return OpenAI(api_key=api_key)

supabase = init_supabase()
openai_client = init_openai()

# Initialize session state
def init_session_state():
    if 'interview_started' not in st.session_state:
        st.session_state.interview_started = False
    if 'current_question_num' not in st.session_state:
        st.session_state.current_question_num = 1
    if 'current_question' not in st.session_state:
        st.session_state.current_question = ""
    if 'interview_data' not in st.session_state:
        st.session_state.interview_data = {}
    if 'all_qa' not in st.session_state:
        st.session_state.all_qa = []
    if 'total_questions' not in st.session_state:
        st.session_state.total_questions = 10
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    if 'interview_id' not in st.session_state:
        st.session_state.interview_id = None

init_session_state()

# Database Functions
class DatabaseManager:
    """Manage Supabase database operations"""
    
    @staticmethod
    def create_tables():
        """Create necessary tables - Run this SQL in Supabase SQL Editor once"""
        sql_script = """
        -- Interviews table
        CREATE TABLE IF NOT EXISTS interviews (
            id BIGSERIAL PRIMARY KEY,
            candidate_name VARCHAR(255) NOT NULL,
            job_title VARCHAR(255) NOT NULL,
            interview_type VARCHAR(50) NOT NULL,
            status VARCHAR(50) DEFAULT 'completed',
            final_score DECIMAL(4,2),
            start_time TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        -- Questions table
        CREATE TABLE IF NOT EXISTS questions (
            id BIGSERIAL PRIMARY KEY,
            interview_id BIGINT REFERENCES interviews(id) ON DELETE CASCADE,
            question_number INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            answer TEXT,
            score DECIMAL(4,2),
            feedback TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        return sql_script
    
    @staticmethod
    def save_interview(interview_data):
        """Save interview to Supabase"""
        if not supabase:
            return None
        
        try:
            # Insert interview
            interview_response = supabase.table('interviews').insert({
                'candidate_name': interview_data['candidate_name'],
                'job_title': interview_data['job_title'],
                'interview_type': interview_data['interview_type'],
                'status': 'completed',
                'final_score': interview_data['final_score'],
                'start_time': interview_data['start_time'],
                'completed_at': datetime.now().isoformat()
            }).execute()
            
            if not interview_response.data:
                st.error("Failed to save interview")
                return None
            
            interview_id = interview_response.data[0]['id']
            
            # Insert questions
            questions_data = []
            for qa in interview_data['qa_pairs']:
                questions_data.append({
                    'interview_id': interview_id,
                    'question_number': qa['number'],
                    'question_text': qa['question'],
                    'answer': qa['answer'],
                    'score': qa['score'],
                    'feedback': qa['feedback']
                })
            
            supabase.table('questions').insert(questions_data).execute()
            
            return interview_id
        except Exception as e:
            st.error(f"Error saving interview: {str(e)}")
            return None
    
    @staticmethod
    def get_all_interviews():
        """Get all interviews from Supabase"""
        if not supabase:
            return []
        
        try:
            response = supabase.table('interviews').select('*').order('created_at', desc=True).execute()
            return response.data if response.data else []
        except Exception as e:
            st.error(f"Error fetching interviews: {str(e)}")
            return []
    
    @staticmethod
    def get_questions(interview_id):
        """Get questions for an interview"""
        if not supabase:
            return []
        
        try:
            response = supabase.table('questions').select('*').eq('interview_id', interview_id).order('question_number').execute()
            return response.data if response.data else []
        except Exception as e:
            st.error(f"Error fetching questions: {str(e)}")
            return []

db = DatabaseManager()

# Note: Run the SQL script from DatabaseManager.create_tables() in Supabase SQL Editor once to create tables

# Helper Functions
def extract_text_from_pdf(pdf_file):
    """Extract text from PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_file.read()))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {str(e)}")
        return ""

def text_to_speech(text):
    """Convert text to speech and play"""
    try:
        tts = gTTS(text=text, lang='en', slow=False)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
            tts.save(fp.name)
            st.audio(fp.name, format='audio/mp3')
            return True
    except Exception as e:
        st.error(f"Error with text-to-speech: {str(e)}")
        return False

def speech_to_text():
    """Convert speech to text"""
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            st.info("🎤 Listening... Speak now!")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio = recognizer.listen(source, timeout=30, phrase_time_limit=60)
            st.success("✅ Processing audio...")
            text = recognizer.recognize_google(audio)
            return text
    except sr.WaitTimeoutError:
        st.error("⏱️ Timeout - No speech detected")
        return None
    except sr.UnknownValueError:
        st.error("❌ Could not understand audio")
        return None
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None

# OpenAI Functions
def ask_ai_question(resume, jd, interview_type, question_num, conversation_history):
    """Ask OpenAI to generate next question based on context"""
    if not openai_client:
        return "What is your experience with the technologies mentioned in the job description?"
    
    # Build conversation context
    context = ""
    if conversation_history:
        context = "\n\nPrevious Questions and Answers:\n"
        for i, qa in enumerate(conversation_history, 1):
            context += f"\nQ{i}: {qa['question']}\nA{i}: {qa['answer']}\n"
    
    prompt = f"""You are conducting a {interview_type} interview. 

Job Description:
{jd}

Candidate's Resume:
{resume}

{context}

This is question {question_num} out of 10 questions total.

Generate ONE relevant {interview_type} interview question that:
- Is appropriate for question number {question_num} (start easier, get progressively harder)
- Relates to the job requirements
- Builds upon previous answers if any
- Is specific and clear
- For technical interviews: focus on skills, problem-solving, coding experience
- For HR interviews: focus on soft skills, culture fit, scenarios

Return ONLY the question text, nothing else."""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert technical and HR interviewer."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"Error generating question: {str(e)}")
        return "Tell me about your relevant experience for this role."

def evaluate_answer(question, answer, jd, interview_type):
    """Evaluate the candidate's answer using OpenAI"""
    if not openai_client:
        return 7, "Good answer with relevant details."
    
    prompt = f"""Evaluate this {interview_type} interview answer.

Job Requirements:
{jd}

Question: {question}
Answer: {answer}

Provide:
1. A score from 0-10 (0=poor, 10=excellent)
2. Brief constructive feedback (2-3 sentences)

Consider:
- Relevance to the question
- Depth of knowledge
- Communication clarity
- Alignment with job requirements

Return ONLY valid JSON in this exact format:
{{"score": 8, "feedback": "Your feedback here"}}"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert interview evaluator. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.5
        )
        
        result_text = response.choices[0].message.content.strip()
        # Clean up the response if it has markdown code blocks
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].strip()
        
        result = json.loads(result_text)
        return result['score'], result['feedback']
    except Exception as e:
        st.error(f"Error evaluating: {str(e)}")
        return 7, "Unable to provide detailed feedback at this time."

# Main Application
def main():
    st.markdown('<div class="main-header">🎯 AI Interview System</div>', unsafe_allow_html=True)
    
    # Sidebar with info
    with st.sidebar:
        st.markdown("### 📊 System Status")
        st.markdown(f"**Supabase:** {'✅ Connected' if supabase else '❌ Not Connected'}")
        st.markdown(f"**OpenAI:** {'✅ Ready' if openai_client else '❌ Not Configured'}")
        
        st.markdown("---")
        st.markdown("### 📖 How It Works")
        st.markdown("""
        1. Upload resume & job description
        2. AI asks 10 questions one-by-one
        3. Answer via text or voice
        4. Get instant feedback
        5. View final results
        """)
        
        st.markdown("---")
        if st.button("📚 View Past Interviews"):
            st.session_state.show_history = True
        
        st.markdown("---")
        st.markdown("### ⚙️ Setup Tables")
        if st.button("📋 Show SQL Script"):
            st.code(DatabaseManager.create_tables(), language='sql')
    
    # Show history if requested
    if 'show_history' in st.session_state and st.session_state.show_history:
        show_interview_history()
        if st.button("⬅️ Back to Interview"):
            st.session_state.show_history = False
            st.rerun()
        return
    
    # Setup Phase
    if not st.session_state.interview_started:
        st.markdown("### 📋 Interview Setup")
        
        col1, col2 = st.columns(2)
        
        with col1:
            candidate_name = st.text_input("👤 Candidate Name", placeholder="John Doe")
            job_title = st.text_input("💼 Job Title", placeholder="Software Engineer")
            interview_type = st.selectbox("📝 Interview Type", ["technical", "hr"])
        
        with col2:
            st.markdown("##### 📄 Upload Documents")
            resume_file = st.file_uploader("Resume (PDF or TXT)", type=['pdf', 'txt'])
            jd_file = st.file_uploader("Job Description (PDF or TXT)", type=['pdf', 'txt'])
        
        st.markdown("---")
        
        if st.button("🚀 Start Interview", type="primary", use_container_width=True):
            if candidate_name and job_title and resume_file and jd_file:
                # Extract text from files
                if resume_file.type == 'application/pdf':
                    resume_text = extract_text_from_pdf(resume_file)
                else:
                    resume_text = resume_file.read().decode('utf-8')
                
                if jd_file.type == 'application/pdf':
                    jd_text = extract_text_from_pdf(jd_file)
                else:
                    jd_text = jd_file.read().decode('utf-8')
                
                # Store interview data
                st.session_state.interview_data = {
                    'candidate_name': candidate_name,
                    'job_title': job_title,
                    'interview_type': interview_type,
                    'resume': resume_text,
                    'jd': jd_text,
                    'start_time': datetime.now().isoformat()
                }
                
                # Generate first question
                with st.spinner("🤖 AI is preparing the first question..."):
                    first_question = ask_ai_question(
                        resume_text, 
                        jd_text, 
                        interview_type, 
                        1, 
                        []
                    )
                    st.session_state.current_question = first_question
                    st.session_state.interview_started = True
                    st.session_state.current_question_num = 1
                
                st.success("✅ Interview Started!")
                st.rerun()
            else:
                st.warning("⚠️ Please fill all fields and upload both documents")
    
    # Interview Phase
    else:
        if st.session_state.current_question_num <= st.session_state.total_questions:
            # Progress
            progress = (st.session_state.current_question_num - 1) / st.session_state.total_questions
            st.progress(progress, text=f"Question {st.session_state.current_question_num} of {st.session_state.total_questions}")
            
            # Display current question
            st.markdown(f"""
            <div class="question-box">
                <h3>Question {st.session_state.current_question_num}</h3>
                <p style="font-size: 1.2rem; margin-top: 1rem;">{st.session_state.current_question}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Audio button for question
            col1, col2, col3 = st.columns([2, 1, 1])
            with col2:
                if st.button("🔊 Hear Question", use_container_width=True):
                    text_to_speech(st.session_state.current_question)
            
            # Answer input
            st.markdown("### 💬 Your Answer")
            answer = st.text_area(
                "Type your answer here:",
                height=200,
                key=f"answer_{st.session_state.current_question_num}",
                placeholder="Provide a detailed answer..."
            )
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                if st.button("🎤 Record Voice Answer", use_container_width=True):
                    voice_answer = speech_to_text()
                    if voice_answer:
                        st.session_state[f"answer_{st.session_state.current_question_num}"] = voice_answer
                        st.rerun()
            
            with col2:
                if st.button("➡️ Submit Answer", type="primary", use_container_width=True):
                    if answer and answer.strip():
                        # Evaluate answer
                        with st.spinner("🤖 AI is evaluating your answer..."):
                            score, feedback = evaluate_answer(
                                st.session_state.current_question,
                                answer,
                                st.session_state.interview_data['jd'],
                                st.session_state.interview_data['interview_type']
                            )
                        
                        # Store Q&A
                        qa_pair = {
                            'number': st.session_state.current_question_num,
                            'question': st.session_state.current_question,
                            'answer': answer,
                            'score': score,
                            'feedback': feedback
                        }
                        st.session_state.all_qa.append(qa_pair)
                        st.session_state.conversation_history.append({
                            'question': st.session_state.current_question,
                            'answer': answer
                        })
                        
                        # Show immediate feedback
                        st.markdown(f"""
                        <div class="answer-box">
                            <h4>✅ Answer Submitted!</h4>
                            <p><strong>Score:</strong> {score}/10</p>
                            <p><strong>Feedback:</strong> {feedback}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Move to next question
                        if st.session_state.current_question_num < st.session_state.total_questions:
                            st.session_state.current_question_num += 1
                            
                            # Generate next question
                            with st.spinner("🤖 Preparing next question..."):
                                next_question = ask_ai_question(
                                    st.session_state.interview_data['resume'],
                                    st.session_state.interview_data['jd'],
                                    st.session_state.interview_data['interview_type'],
                                    st.session_state.current_question_num,
                                    st.session_state.conversation_history
                                )
                                st.session_state.current_question = next_question
                            
                            st.info("Moving to next question in 3 seconds...")
                            import time
                            time.sleep(3)
                            st.rerun()
                        else:
                            st.session_state.current_question_num += 1
                            st.rerun()
                    else:
                        st.warning("⚠️ Please provide an answer before submitting")
        
        # Results Phase
        else:
            st.markdown("### 🎉 Interview Completed!")
            
            # Calculate final score
            total_score = sum([qa['score'] for qa in st.session_state.all_qa])
            avg_score = total_score / len(st.session_state.all_qa)
            percentage = (avg_score / 10) * 100
            
            # Display score
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.markdown(f"""
                <div class="score-card">
                    <h1 style="font-size: 4rem; margin: 0;">{avg_score:.1f}/10</h1>
                    <h3 style="margin: 1rem 0;">Overall Score</h3>
                    <p style="font-size: 1.5rem;">{percentage:.0f}%</p>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Detailed results
            st.markdown("### 📊 Detailed Results")
            
            for qa in st.session_state.all_qa:
                with st.expander(f"Question {qa['number']}: {qa['question'][:100]}... (Score: {qa['score']}/10)"):
                    st.markdown(f"**Question:** {qa['question']}")
                    st.markdown(f"**Your Answer:** {qa['answer']}")
                    st.markdown(f"**Score:** {qa['score']}/10")
                    st.markdown(f"**Feedback:** {qa['feedback']}")
            
            # Save to database
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("💾 Save to Database", use_container_width=True):
                    interview_data = st.session_state.interview_data.copy()
                    interview_data['qa_pairs'] = st.session_state.all_qa
                    interview_data['final_score'] = avg_score
                    
                    interview_id = db.save_interview(interview_data)
                    if interview_id:
                        st.success(f"✅ Saved! Interview ID: {interview_id}")
                        st.session_state.interview_id = interview_id
                    else:
                        st.error("❌ Failed to save to database")
            
            with col2:
                if st.button("📥 Download Results (JSON)", use_container_width=True):
                    results = {
                        'candidate': st.session_state.interview_data['candidate_name'],
                        'job_title': st.session_state.interview_data['job_title'],
                        'interview_type': st.session_state.interview_data['interview_type'],
                        'final_score': avg_score,
                        'percentage': percentage,
                        'qa_pairs': st.session_state.all_qa,
                        'date': st.session_state.interview_data['start_time']
                    }
                    st.download_button(
                        "Download",
                        data=json.dumps(results, indent=2),
                        file_name=f"interview_{st.session_state.interview_data['candidate_name']}_{datetime.now().strftime('%Y%m%d')}.json",
                        mime="application/json",
                        use_container_width=True
                    )
            
            st.markdown("---")
            if st.button("🔄 Start New Interview", type="primary", use_container_width=True):
                # Reset everything
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

def show_interview_history():
    """Display past interviews"""
    st.markdown("### 📚 Interview History")
    
    interviews = db.get_all_interviews()
    
    if interviews:
        for interview in interviews:
            with st.expander(f"👤 {interview['candidate_name']} - {interview['job_title']} (Score: {interview['final_score']:.1f}/10)"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**Type:** {interview['interview_type'].title()}")
                    created_at = interview.get('created_at', '')
                    if created_at:
                        st.write(f"**Date:** {created_at[:10]}")
                
                with col2:
                    st.write(f"**Score:** {interview['final_score']:.1f}/10")
                    percentage = (interview['final_score'] / 10) * 100
                    st.write(f"**Percentage:** {percentage:.0f}%")
                
                with col3:
                    st.write(f"**Status:** {interview['status'].title()}")
                
                # Show questions
                questions = db.get_questions(interview['id'])
                if questions:
                    st.markdown("#### Questions & Answers")
                    for q in questions:
                        st.markdown(f"**Q{q['question_number']}:** {q['question_text']}")
                        st.markdown(f"**A:** {q['answer']}")
                        st.markdown(f"**Score:** {q['score']}/10 | **Feedback:** {q['feedback']}")
                        st.markdown("---")
    else:
        st.info("No past interviews found")

if __name__ == "__main__":
    main()