import streamlit as st
import json
import google.generativeai as genai
from datetime import datetime
import os
from typing import Dict, List, Any

# Configure Gemini AI
def configure_gemini():
    """Configure Gemini AI with API key from Streamlit secrets"""
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        st.error("GEMINI_API_KEY not found in Streamlit secrets!")
        return None
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-flash')



def load_questions_from_json():
    """Load questions from local bpr.json file"""
    try:
        with open('bpr.json', 'r') as file:
            data = json.load(file)
            # Restructure the data to organize by sections
            sections = {}
            questionnaire = data.get('bpr_questionnaire', {})
            
            for section_key, questions in questionnaire.items():
                # Clean up section names
                section_name = section_key.replace('_questions', '').replace('_', ' ').title()
                if section_name == 'Company Questions':
                    section_name = 'Company'
                elif section_name == 'Gl Questions':
                    section_name = 'General Ledger'
                elif section_name == 'Financial Reports Questions':
                    section_name = 'Financial Reports'
                elif section_name == 'Cash Questions':
                    section_name = 'Cash Management'
                elif section_name == 'Ap Questions':
                    section_name = 'Accounts Payable'
                elif section_name == 'Ar Questions':
                    section_name = 'Accounts Receivable'
                elif section_name == 'Pea Questions':
                    section_name = 'Prepaid Expense Amortization'
                
                sections[section_name] = questions
            
            return sections
    except FileNotFoundError:
        st.error("bpr.json file not found in the current directory!")
        return {}
    except json.JSONDecodeError:
        st.error("Invalid JSON format in bpr.json!")
        return {}

def validate_response(model, question, user_answer, context=None):
    """Validate user response and generate follow-up questions if needed"""
    if not model:
        return True, []
    
    try:
        prompt = f"""
        You are helping with a BRP (Business Requirements Planning) questionnaire for ERP implementation.
        
        Question: {question}
        Context: {context if context else 'No additional context provided'}
        User's Answer: {user_answer}
        
        Evaluate if the user's answer is:
        1. Clear and specific enough to answer the question
        2. Relevant to the question asked
        3. Contains sufficient detail for ERP implementation planning
        
        If the answer is adequate, respond with: "ADEQUATE"
        
        If the answer needs clarification, respond with "NEEDS_FOLLOWUP" followed by 1-2 specific follow-up questions that will help get better information. Format follow-up questions as a JSON array.
        
        Examples of inadequate answers that need follow-up:
        - Vague answers like "SQL" when asked about database systems (should specify which SQL database)
        - "Yes" or "No" without details when more context is needed
        - Irrelevant or off-topic responses
        
        Be strict but fair in your evaluation. Only mark as adequate if the answer truly provides the information needed for ERP planning.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        if response_text.startswith("ADEQUATE"):
            return True, []
        elif response_text.startswith("NEEDS_FOLLOWUP"):
            try:
                # Extract JSON part
                json_part = response_text.split("NEEDS_FOLLOWUP", 1)[1].strip()
                followup_questions = json.loads(json_part)
                return False, followup_questions if isinstance(followup_questions, list) else []
            except:
                # Fallback: extract questions manually
                lines = response_text.split('\n')
                questions = []
                for line in lines[1:]:  # Skip first line
                    line = line.strip()
                    if line and ('?' in line):
                        question = line.strip('- "[],"')
                        if question:
                            questions.append(question)
                return False, questions[:2]
        
        return True, []  # Default to adequate if unclear
        
    except Exception as e:
        st.error(f"Error validating response: {str(e)}")
        return True, []  # Default to adequate if error


def initialize_session_state():
    """Initialize session state variables"""
    if 'sections' not in st.session_state:
        st.session_state.sections = {}
    if 'current_section' not in st.session_state:
        st.session_state.current_section = ""
    if 'current_question_index' not in st.session_state:
        st.session_state.current_question_index = 0
    if 'responses' not in st.session_state:
        st.session_state.responses = {}
    if 'section_progress' not in st.session_state:
        st.session_state.section_progress = {}
    if 'completed_sections' not in st.session_state:
        st.session_state.completed_sections = set()
    if 'followup_mode' not in st.session_state:
        st.session_state.followup_mode = False
    if 'followup_questions' not in st.session_state:
        st.session_state.followup_questions = []
    if 'followup_answers' not in st.session_state:
        st.session_state.followup_answers = []
    if 'current_followup_index' not in st.session_state:
        st.session_state.current_followup_index = 0
    if 'original_answer' not in st.session_state:
        st.session_state.original_answer = ""
    if 'editing_mode' not in st.session_state:
        st.session_state.editing_mode = False
    if 'editing_question' not in st.session_state:
        st.session_state.editing_question = None

def get_section_description(section_name):
    """Get description for each section"""
    descriptions = {
        'Company': 'basic company information and project details',
        'Security': 'security settings and access controls',
        'General Ledger': 'general ledger configuration and accounting settings',
        'Financial Reports': 'financial reporting requirements',
        'Cash Management': 'cash and bank account management',
        'Accounts Payable': 'supplier and payment management',
        'Purchasing': 'purchasing process and workflow',
        'Accounts Receivable': 'customer and invoice management',
        'Order Entry': 'sales order and invoicing process',
        'Prepaid Expense Amortization': 'prepaid expense handling and amortization'
    }
    return descriptions.get(section_name, 'system configuration')

def display_progress_sidebar():
    """Display progress for each section in sidebar"""
    with st.sidebar:
        st.header("📊 Progress Tracker")
        
        total_questions = 0
        total_answered = 0
        
        for section_name, questions in st.session_state.sections.items():
            section_total = len(questions)
            section_answered = len([q for q in questions if q.get('answered', False)])
            
            total_questions += section_total
            total_answered += section_answered
            
            # Progress bar for this section
            progress = section_answered / section_total if section_total > 0 else 0
            
            # Section status emoji
            if section_answered == section_total:
                status = "✅"
                st.session_state.completed_sections.add(section_name)
            elif section_answered > 0:
                status = "🔄"
            else:
                status = "⭕"
            
            st.markdown(f"**{status} {section_name}**")
            st.progress(progress)
            st.caption(f"{section_answered}/{section_total} completed")
            st.markdown("---")
        
        # Overall progress
        overall_progress = total_answered / total_questions if total_questions > 0 else 0
        st.markdown("**🎯 Overall Progress**")
        st.progress(overall_progress)
        st.caption(f"{total_answered}/{total_questions} total questions")

def save_response(section, question_index, answer, followup_data=None):
    """Save response for a question"""
    if section not in st.session_state.responses:
        st.session_state.responses[section] = {}
    
    st.session_state.responses[section][question_index] = {
        'answer': answer,
        'followup': followup_data or [],
        'timestamp': datetime.now().isoformat()
    }
    
    # Mark question as answered
    st.session_state.sections[section][question_index]['answered'] = True

def main():
    st.title("🤖 BRP Questionnaire Assistant")
    st.markdown("*Business Requirements Planning for ERP Implementation*")
    st.markdown("---")
    
    # Initialize session state
    initialize_session_state()
    
    # Configure Gemini
    model = configure_gemini()
    if not model:
        st.stop()
    
    # Load questions
    if not st.session_state.sections:
        st.session_state.sections = load_questions_from_json()
        if not st.session_state.sections:
            st.stop()
    
    # Display progress sidebar
    display_progress_sidebar()
    
    # Check if all sections are completed
    all_sections = list(st.session_state.sections.keys())
    if len(st.session_state.completed_sections) == len(all_sections):
        display_summary()
        return
    
    # Section selection or continuation
    if not st.session_state.current_section or st.session_state.editing_mode:
        if not st.session_state.editing_mode:
            display_section_selection()
        else:
            display_editing_interface()
        return
    
    # Current section and question
    current_section = st.session_state.current_section
    questions = st.session_state.sections[current_section]
    current_q_index = st.session_state.current_question_index
    
    # Check if section is completed
    if current_q_index >= len(questions):
        st.success(f"✅ {current_section} section completed!")
        st.balloons()
        
        # Reset for next section
        st.session_state.current_section = ""
        st.session_state.current_question_index = 0
        st.session_state.followup_mode = False
        
        if st.button("Continue to Next Section"):
            st.rerun()
        return
    
    current_question = questions[current_q_index]
    
    # Display current section and question
    st.header(f"📋 {current_section}")
    st.markdown(f"**Question {current_q_index + 1} of {len(questions)}**")
    st.markdown(f"### {current_question['question']}")
    
    if current_question.get('context'):
        st.info(f"**Context:** {current_question['context']}")
    
    # Handle follow-up mode
    if st.session_state.followup_mode:
        display_followup_interface(model, current_section, current_q_index, current_question)
    else:
        display_main_question_interface(model, current_section, current_q_index, current_question)

def display_section_selection():
    """Display section selection interface"""
    st.header("📚 Select a Section to Begin")
    
    incomplete_sections = []
    for section_name in st.session_state.sections.keys():
        if section_name not in st.session_state.completed_sections:
            incomplete_sections.append(section_name)
    
    if not incomplete_sections:
        st.success("All sections completed!")
        return
    
    for section_name in incomplete_sections:
        questions = st.session_state.sections[section_name]
        answered_count = len([q for q in questions if q.get('answered', False)])
        total_count = len(questions)
        
        description = get_section_description(section_name)
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{section_name}**")
            st.caption(f"Questions about {description}")
            st.caption(f"Progress: {answered_count}/{total_count} questions")
        
        with col2:
            if st.button(f"Start", key=f"start_{section_name}"):
                st.session_state.current_section = section_name
                # Find first unanswered question
                for i, q in enumerate(questions):
                    if not q.get('answered', False):
                        st.session_state.current_question_index = i
                        break
                st.rerun()
        
        st.markdown("---")

def display_main_question_interface(model, section, q_index, question):
    """Display main question interface"""
    # Check if already answered
    existing_answer = ""
    if section in st.session_state.responses and q_index in st.session_state.responses[section]:
        existing_answer = st.session_state.responses[section][q_index]['answer']
        st.info(f"**Current Answer:** {existing_answer}")
    
    user_answer = st.text_area(
        "Your Answer:",
        value=existing_answer,
        height=120,
        key=f"answer_{section}_{q_index}",
        help="Provide a detailed answer to help with ERP implementation planning"
    )
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if st.button("✅ Submit Answer", type="primary"):
            if user_answer.strip():
                # Validate response
                is_adequate, followup_questions = validate_response(
                    model, question['question'], user_answer, question.get('context')
                )
                
                if is_adequate:
                    # Save response and move to next question
                    save_response(section, q_index, user_answer.strip())
                    st.session_state.current_question_index += 1
                    st.success("Answer saved! Moving to next question...")
                    st.rerun()
                else:
                    # Enter follow-up mode
                    st.session_state.followup_mode = True
                    st.session_state.followup_questions = followup_questions
                    st.session_state.followup_answers = []
                    st.session_state.current_followup_index = 0
                    st.session_state.original_answer = user_answer.strip()
                    st.rerun()
            else:
                st.warning("Please provide an answer before submitting.")
    
    with col2:
        if st.button("⏭️ Skip"):
            save_response(section, q_index, "Skipped")
            st.session_state.current_question_index += 1
            st.rerun()
    
    with col3:
        if st.button("🏠 Back to Sections"):
            st.session_state.current_section = ""
            st.session_state.followup_mode = False
            st.rerun()

def display_followup_interface(model, section, q_index, question):
    """Display follow-up questions interface"""
    st.markdown("---")
    st.markdown("### 🤔 Let's clarify your answer")
    st.info(f"**Your original answer:** {st.session_state.original_answer}")
    
    if st.session_state.current_followup_index < len(st.session_state.followup_questions):
        current_followup = st.session_state.followup_questions[st.session_state.current_followup_index]
        
        st.markdown(f"**Follow-up Question {st.session_state.current_followup_index + 1}:** {current_followup}")
        
        followup_answer = st.text_area(
            "Additional Information:",
            key=f"followup_{section}_{q_index}_{st.session_state.current_followup_index}",
            height=100
        )
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("Next", key="next_followup"):
                if followup_answer.strip():
                    st.session_state.followup_answers.append({
                        "question": current_followup,
                        "answer": followup_answer.strip()
                    })
                    st.session_state.current_followup_index += 1
                    st.rerun()
                else:
                    st.warning("Please provide an answer before proceeding.")
        
        with col2:
            if st.button("Use Original Answer", key="use_original"):
                # Accept original answer as is
                save_response(section, q_index, st.session_state.original_answer)
                reset_followup_state()
                st.session_state.current_question_index += 1
                st.rerun()
    
    else:
        # All follow-up questions completed
        st.markdown("### ✅ Follow-up Complete")
        
        # Combine all answers
        combined_answer = st.session_state.original_answer + "\n\nAdditional Details:\n"
        for i, fa in enumerate(st.session_state.followup_answers):
            combined_answer += f"• {fa['question']}: {fa['answer']}\n"
        
        st.text_area("Final Combined Answer:", value=combined_answer, height=150, disabled=True)
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("✅ Accept Final Answer", type="primary"):
                followup_data = st.session_state.followup_answers.copy()
                save_response(section, q_index, combined_answer, followup_data)
                reset_followup_state()
                st.session_state.current_question_index += 1
                st.rerun()
        
        with col2:
            if st.button("🔄 Start Over"):
                reset_followup_state()
                st.rerun()

def reset_followup_state():
    """Reset follow-up related session state"""
    st.session_state.followup_mode = False
    st.session_state.followup_questions = []
    st.session_state.followup_answers = []
    st.session_state.current_followup_index = 0
    st.session_state.original_answer = ""

def display_editing_interface():
    """Display interface for editing responses"""
    st.header("✏️ Edit Response")
    
    edit_section, edit_q_index = st.session_state.editing_question
    question = st.session_state.sections[edit_section][edit_q_index]
    current_response = st.session_state.responses[edit_section][edit_q_index]
    
    st.markdown(f"**Section:** {edit_section}")
    st.markdown(f"**Question:** {question['question']}")
    if question.get('context'):
        st.info(f"**Context:** {question['context']}")
    
    # Show original answer for reference
    with st.expander("📖 View Original Answer"):
        st.text(current_response['answer'])
        if current_response.get('followup'):
            st.markdown("**Follow-up clarifications:**")
            for fu in current_response['followup']:
                st.markdown(f"- {fu['question']}: {fu['answer']}")
    
    # Edit field with current answer
    new_answer = st.text_area(
        "Edit Your Answer:",
        value=current_response['answer'],
        height=150,
        key=f"edit_field_{edit_section}_{edit_q_index}"
    )
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("💾 Save Changes", type="primary", key="save_changes"):
            if new_answer.strip():
                # Update the response
                st.session_state.responses[edit_section][edit_q_index]['answer'] = new_answer.strip()
                st.session_state.responses[edit_section][edit_q_index]['timestamp'] = datetime.now().isoformat()
                
                # Exit editing mode
                st.session_state.editing_mode = False
                st.session_state.editing_question = None
                
                st.success("✅ Answer updated successfully!")
                st.rerun()
            else:
                st.warning("Please provide an answer before saving.")
    
    with col2:
        if st.button("❌ Cancel", key="cancel_edit"):
            st.session_state.editing_mode = False
            st.session_state.editing_question = None
            st.rerun()

def display_summary():
    """Display final summary with all responses"""
    st.header("🎉 Questionnaire Completed!")
    st.success("All sections have been completed. Review your responses below.")
    
    # Summary statistics
    total_questions = sum(len(questions) for questions in st.session_state.sections.values())
    st.metric("Total Questions Completed", total_questions)
    
    st.markdown("---")
    
    # Display all responses by section
    for section_name, questions in st.session_state.sections.items():
        with st.expander(f"📋 {section_name} ({len(questions)} questions)", expanded=False):
            if section_name in st.session_state.responses:
                responses = st.session_state.responses[section_name]
                
                for q_index, question in enumerate(questions):
                    if q_index in responses:
                        response = responses[q_index]
                        
                        st.markdown(f"**Q{q_index + 1}:** {question['question']}")
                        if question.get('context'):
                            st.caption(f"Context: {question['context']}")
                        
                        st.markdown(f"**Answer:** {response['answer']}")
                        
                        # Edit button
                        if st.button(f"✏️ Edit", key=f"edit_{section_name}_{q_index}"):
                            st.session_state.editing_mode = True
                            st.session_state.editing_question = (section_name, q_index)
                            st.rerun()
                        
                        # Show follow-up details if any
                        if response.get('followup'):
                            st.markdown("*Follow-up clarifications:*")
                            for fu in response['followup']:
                                st.markdown(f"- {fu['question']}: {fu['answer']}")
                        
                        st.markdown("---")
    
    # Download option
    st.markdown("### 💾 Download Results")
    
    # Prepare data for download
    download_data = {
        "questionnaire_responses": {},
        "completion_date": datetime.now().isoformat(),
        "total_questions": total_questions
    }
    
    for section_name, questions in st.session_state.sections.items():
        section_responses = []
        if section_name in st.session_state.responses:
            responses = st.session_state.responses[section_name]
            
            for q_index, question in enumerate(questions):
                response_data = {
                    "question": question['question'],
                    "context": question.get('context'),
                    "category": question.get('category', section_name)
                }
                
                if q_index in responses:
                    response = responses[q_index]
                    response_data.update({
                        "answer": response['answer'],
                        "followup_clarifications": response.get('followup', []),
                        "timestamp": response['timestamp']
                    })
                else:
                    response_data["answer"] = "Not answered"
                
                section_responses.append(response_data)
        
        download_data["questionnaire_responses"][section_name] = section_responses
    
    output_json = json.dumps(download_data, indent=2)
    
    st.download_button(
        label="📥 Download Complete Responses (JSON)",
        data=output_json,
        file_name=f"brp_responses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )
    
    # Restart option
    if st.button("🔄 Start New Questionnaire"):
        # Clear all session state except sections
        for key in list(st.session_state.keys()):
            if key != 'sections':
                del st.session_state[key]
        st.rerun()

if __name__ == "__main__":
    main()