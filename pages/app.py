import os
import base64
from datetime import datetime, timedelta

import streamlit as st
from groq import Groq
from meldrx_fhir_client import FHIRClient
from utils import preprocess_audio, split_audio


st.set_page_config(
    page_title="SageScript AI",
    page_icon="🎙️",
    layout="wide"  # Use wide layout for better space utilization
)

class App:
    def __init__(self):
        access_token = st.session_state['token']['access_token']
        workspace_id = st.session_state['workspace_id']
        fhir_endpoint = f'https://app.meldrx.com/api/fhir/{workspace_id}'
        self.fhir = FHIRClient(
            base_url=fhir_endpoint,
            access_token=access_token,
            access_token_type='Bearer'
        )
        self.groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

    def initialize_session_state(self):
        if 'patient_id' not in st.session_state:
            st.session_state['patient_id'] = None
        if 'transcription' not in st.session_state:
            st.session_state['transcription'] = ""
        if 'editable_report' not in st.session_state:
            st.session_state['editable_report'] = "No consultation recorded yet"
        if 'patient_context' not in st.session_state:
            st.session_state['patient_context'] = ""
        if 'audio_processed' not in st.session_state:
            st.session_state['audio_processed'] = False

    def reset_session_state(self):
        st.session_state['transcription'] = ""
        st.session_state['editable_report'] = "No consultation recorded yet"
        st.session_state['patient_context'] = ""
        st.session_state['audio_processed'] = False
    
    def create_context_selectors(self):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            time_range = st.selectbox(
                "Historical Data Range",
                ["Last 3 months", "Last year", "Last 2 years"],
                help="Select time range for historical data"
            )
        
        with col2:
            context_types = st.multiselect(
                "Include Context",
                ["Allergies", "Medications", "Previous Conditions", "Previous Reports"],
                default=["Allergies", "Medications"],
                help="Select types of historical data to include"
            )
        
        with col3:
            consultation_type = st.selectbox(
                "Consultation Type",
                ["Initial Visit", "Follow-up", "Specialist Referral", "Regular Check-up"],
                help="Select the type of consultation"
            )
        
        return time_range, context_types, consultation_type

    def display_patient_context(self, patient, time_range, context_types):
        if time_range != "None":
            with st.expander("Patient Context", expanded=True):
                cols = st.columns(len(context_types))
                for i, context_type in enumerate(context_types):
                    with cols[i]:
                        st.subheader(context_type)
                        # Placeholder for actual FHIR queries
                        st.text("Loading context...")
                        
    def transcribe_chunk(self, audio_path: str) -> str:
        """Transcribe a single audio chunk using Groq API."""
        with open(audio_path, "rb") as file:
            transcription = self.groq_client.audio.transcriptions.create(
                file=(audio_path, file.read()),
                model="whisper-large-v3-turbo",
                response_format="json",
                temperature=0.0
            )
        return transcription.text

    def process_audio(self, audio_file) -> str:
        """Process audio data and return transcription."""
        try:
            processed_audio = preprocess_audio(audio_file)
            chunks = split_audio(processed_audio)
            
            transcriptions = []
            for chunk_path in chunks:
                chunk_text = self.transcribe_chunk(chunk_path)
                transcriptions.append(chunk_text)
                try:
                    os.remove(chunk_path)
                except:
                    pass
            
            try:
                os.remove(processed_audio)
            except:
                pass
                
            return " ".join(transcriptions)
        
        except Exception as e:
            st.error(f"Error processing audio: {str(e)}")
            return ""

    def get_allergies(self, patient_ref):
        results = self.fhir.search_resource('AllergyIntolerance', {'patient': patient_ref})
        if 'entry' not in results or len(results['entry']) == 0:
            return None, None
        
        allergy_list = []
        for entry in results['entry']:
            resource = entry['resource']
            
            # Get allergy name from the code display or text
            allergy_name = resource['code'].get('text', '')
            if not allergy_name and 'coding' in resource['code']:
                allergy_name = resource['code']['coding'][0].get('display', 'Unknown')
                
            # Extract basic information
            allergy_info = {
                'name': allergy_name,
                'type': resource.get('type', ''),
                'category': resource.get('category', []),
                'criticality': resource.get('criticality', ''),
                'clinical_status': resource['clinicalStatus']['coding'][0].get('code', ''),
                'recorded_date': resource.get('recorded_date', '')
            }
            
            allergy_list.append(allergy_info)
    
        allergy_info = "The patient has the following allergies:\n"
        for i, allergy in enumerate(allergy_list, 1):
            allergy_info += f"""
            Name: {allergy['name']}
            Category: {', '.join(allergy['category'])}
            Criticality: {allergy['criticality']}
            Clinical Status: {allergy['clinical_status']}\n
            """
        return allergy_list, allergy_info
        
    def get_conditions(self, patient_ref, timeframe_months=3):
        results = self.fhir.search_resource('Condition', {'patient': patient_ref})
        if 'entry' not in results or len(results['entry']) == 0:
            return None, None, None
        
        # Calculate the cutoff date based on timeframe
        if timeframe_months:
            cutoff_date = (datetime.now() - timedelta(days=30 * timeframe_months)).isoformat()
        
        active_conditions = []
        historical_conditions = []
        
        for entry in results['entry']:
            resource = entry['resource']
            
            # Extract condition information
            condition_info = {
                'name': resource['code']['coding'][0].get('display', ''),
                'clinical_status': resource.get('clinicalStatus', {}).get('coding', [{}])[0].get('code', ''),
                'verification_status': resource.get('verificationStatus', {}).get('coding', [{}])[0].get('code', ''),
                'category': [coding.get('display', '') for cat in resource.get('category', []) 
                            for coding in cat.get('coding', [])],
                'onset_date': resource.get('onsetDateTime', ''),
                'abatement_date': resource.get('abatementDateTime', ''),
                'recorded_date': resource.get('recordedDate', '')
            }
            
            # Determine if condition is active or historical
            if condition_info['clinical_status'] == 'active':
                active_conditions.append(condition_info)
            else:
                # Only include historical conditions within the specified timeframe
                if timeframe_months:
                    if condition_info['recorded_date'] and condition_info['recorded_date'] >= cutoff_date:
                        historical_conditions.append(condition_info)
                else:
                    historical_conditions.append(condition_info)

        # Format the output
        conditions_info = "Patient's Current Medical Conditions:\n"
        if active_conditions:
            for condition in active_conditions:
                conditions_info += f"""
                Condition: {condition['name']}
                Status: {condition['clinical_status']}
                Category: {', '.join(condition['category']) if condition['category'] else 'Not specified'}
                Onset Date: {condition['onset_date']}\n"""
        else:
            conditions_info += "No active medical conditions.\n"
        
        if timeframe_months:
            conditions_info += f"\nResolved Conditions (Past {timeframe_months} months):\n"
        else:
            conditions_info += "\nHistorical Conditions:\n"
        
        if historical_conditions:
            for condition in historical_conditions:
                conditions_info += f"""
                Condition: {condition['name']}
                Status: {condition['clinical_status']}
                Category: {', '.join(condition['category']) if condition['category'] else 'Not specified'}
                Onset Date: {condition['onset_date']}
                Resolved Date: {condition['abatement_date']}\n"""
        else:
            conditions_info += "No historical conditions in the specified timeframe.\n"

        return active_conditions, historical_conditions, conditions_info
        

    def get_medications(self, patient_ref, timeframe_months=3):
        results = self.fhir.search_resource('MedicationRequest', {'patient': patient_ref})
        if 'entry' not in results or len(results['entry']) == 0:
            return None, None, None
        
        # Calculate the cutoff date based on timeframe
        if timeframe_months:
            cutoff_date = (datetime.now() - timedelta(days=30 * timeframe_months)).isoformat()
        
        active_medications = []
        historical_medications = []
        
        for entry in results['entry']:
            resource = entry['resource']
            
            # Extract medication information
            med_info = {
                'id': resource.get('id', ''),
                'status': resource.get('status', ''),
                'category': resource.get('category', [{}])[0].get('coding', [{}])[0].get('display', ''),
                'medication': '',  # Will be filled below
                'authored_date': resource.get('authoredOn', ''),
                'prescriber': resource.get('requester', {}).get('display', ''),
                'reason': [ref.get('display', '') for ref in resource.get('reasonReference', [])]
            }
            
            # Get medication name either from medicationCodeableConcept or medicationReference
            if 'medicationCodeableConcept' in resource:
                if 'coding' in resource['medicationCodeableConcept']:
                    med_info['medication'] = resource['medicationCodeableConcept']['coding'][0].get('display', '')
                else:
                    med_info['medication'] = resource['medicationCodeableConcept'].get('text', '')
            elif 'medicationReference' in resource:
                med_info['medication'] = resource['medicationReference'].get('display', '')
                
            # Categorize as active or historical
            if med_info['status'] in ['active', 'intended']:
                active_medications.append(med_info)
            elif med_info['status'] in ['stopped', 'completed']:
                if timeframe_months:
                    if med_info['authored_date'] >= cutoff_date:
                        historical_medications.append(med_info)
                else:
                    historical_medications.append(med_info)
        
        # Format the output
        medications_info = "Patient's Current Medications:\n"
        if active_medications:
            for med in active_medications:
                medications_info += f"""
                Medication: {med['medication']}
                Status: {med['status']}
                Category: {med['category']}
                Prescribed by: {med['prescriber']}
                Prescribed Date: {med['authored_date']}"""
                if med['reason']:
                    medications_info += f"\n            Reason: {', '.join(med['reason'])}\n"
                else:
                    medications_info += "\n"
        else:
            medications_info += "No active medications.\n"
        
        if timeframe_months:
            medications_info += f"\nDiscontinued Medications (Past {timeframe_months} months):\n"
        else:
            medications_info += "\nHistorical Medications:\n"
        
        if historical_medications:
            for med in historical_medications:
                medications_info += f"""
                Medication: {med['medication']}
                Status: {med['status']}
                Category: {med['category']}
                Prescribed by: {med['prescriber']}
                Prescribed Date: {med['authored_date']}"""
                if med['reason']:
                    medications_info += f"\n            Reason: {', '.join(med['reason'])}\n"
                else:
                    medications_info += "\n"
        else:
            medications_info += "No historical medications in the specified timeframe.\n"
        return active_medications, historical_medications, medications_info
        

    def get_reports(self, patient_ref, timeframe_months=3):
        results = self.fhir.search_resource('DiagnosticReport', {'patient': patient_ref})
        if 'entry' not in results or len(results['entry']) == 0:
            return None, None, None
        
        # Calculate the cutoff date based on timeframe
        if timeframe_months:
            cutoff_date = (datetime.now() - timedelta(days=30 * timeframe_months)).isoformat()
        
        recent_reports = []
        older_reports = []
        
        for entry in results['entry']:
            resource = entry['resource']
            if 'presentedForm' in resource and resource['presentedForm']:
                # Get the Base64 encoded data
                encoded_data = resource['presentedForm'][0]['data']
                
                # Decode the Base64 data
                decoded_data = base64.b64decode(encoded_data).decode('utf-8')
                
                # Get basic report metadata
                report_info = {
                    'id': resource.get('id', ''),
                    'status': resource.get('status', ''),
                    'effective_date': resource.get('effectiveDateTime', ''),
                    'performer': resource.get('performer', [{}])[0].get('display', ''),
                    'content': decoded_data,
                    'category': [coding['display'] for category in resource.get('category', [])
                            for coding in category.get('coding', [])],
                    'code': [coding['display'] for coding in resource.get('code', {}).get('coding', [])]
                }
                
                # Categorize based on timeframe
                if timeframe_months and report_info['effective_date']:
                    if report_info['effective_date'] >= cutoff_date:
                        recent_reports.append(report_info)
                    else:
                        older_reports.append(report_info)
                else:
                    recent_reports.append(report_info)

        # Format the output
        reports_info = ""
        if timeframe_months:
            reports_info += f"Diagnostic Reports (Past {timeframe_months} months):\n"
        else:
            reports_info += "All Diagnostic Reports:\n"
        reports_info += "-" * 50 + "\n"
        
        if recent_reports:
            for report in recent_reports:
                reports_info += f"""
    Report Type: {', '.join(report['code'])}
    Status: {report['status']}
    Category: {', '.join(report['category'])}
    Date: {report['effective_date']}
    Provider: {report['performer']}

    Content:
    {report['content']}
    {'=' * 50}\n"""
        else:
            reports_info += "No recent diagnostic reports found.\n"
        
        if timeframe_months and older_reports:
            reports_info += f"\nOlder Reports (Before {timeframe_months} months):\n"
            reports_info += "-" * 50 + "\n"
            for report in older_reports:
                reports_info += f"""
    Report Type: {', '.join(report['code'])}
    Status: {report['status']}
    Category: {', '.join(report['category'])}
    Date: {report['effective_date']}
    Provider: {report['performer']}

    Content:
    {report['content']}
    {'=' * 50}\n"""
        
        return recent_reports, older_reports, reports_info
    
    def get_patient_context(self, patient_ref, timeframe, context_types):
        if timeframe == "Last 3 months":
            timeframe_months = 3
        elif timeframe ==  "Last year":
            timeframe_months = 12
        elif timeframe ==  "Last 2 years":
            timeframe_months = 24
        else:
            timeframe_months = None
            
        patient_context = ""
        
        # Only include allergies if selected
        if "Allergies" in context_types:
            _, allergy_info = self.get_allergies(patient_ref)
            if allergy_info:
                patient_context += allergy_info

        # Only include medications if selected
        if "Medications" in context_types:
            _, _, meds_info = self.get_medications(patient_ref, timeframe_months)
            if meds_info:
                patient_context += meds_info
        
        # Only include conditions if selected
        if "Previous Conditions" in context_types:
            _, _, conditions_info = self.get_conditions(patient_ref, timeframe_months)
            if conditions_info:
                patient_context += conditions_info
        
        # Only include reports if selected
        if "Previous Reports" in context_types:
            _, _, reports_info = self.get_reports(patient_ref, timeframe_months)
            if reports_info:
                patient_context += reports_info

        print(patient_context)
        return patient_context

    def display_patient_history(self, patient_ref, timeframe, context_types):
        if timeframe == "Last 3 months":
            timeframe_months = 3
        elif timeframe == "Last year":
            timeframe_months = 12
        elif timeframe == "Last 2 years":
            timeframe_months = 24
        else:
            timeframe_months = None

        # Get data only for selected context types
        allergy_list = None
        active_meds = historical_meds = None
        active_conditions = historical_conditions = None
        recent_reports = older_reports = None
    
        # Get all data - now unpacking the tuples returned by each function
        if "Allergies" in context_types:
            allergy_list, allergy_info = self.get_allergies(patient_ref)
        if "Medications" in context_types:
            active_meds, historical_meds, meds_info = self.get_medications(patient_ref, timeframe_months)
        if "Previous Conditions" in context_types:
            active_conditions, historical_conditions, conditions_info = self.get_conditions(patient_ref, timeframe_months)
        if "Previous Reports" in context_types:
            recent_reports, older_reports, reports_info = self.get_reports(patient_ref, timeframe_months)

        # Create columns for the table
        st.markdown("### Active Items")
        cols = st.columns([3, 1, 1])
        cols[0].markdown("**Item**")
        cols[1].markdown("**Type**")
        cols[2].markdown("**Date**")

        # Combine all active items
        active_items = []

        # Add active conditions
        if active_conditions is not None:
            for condition in active_conditions:
                active_items.append({
                    "name": condition['name'],
                    "type": "Condition",
                    "date": condition['onset_date'],
                    "details": condition
                })

        # Add active medications
        if active_meds is not None:
            for med in active_meds:
                active_items.append({
                    "name": med['medication'],
                    "type": "Medication",
                    "date": med['authored_date'],
                    "details": med
                })

        # Add allergies
        if allergy_list is not None:
            for allergy in allergy_list:
                active_items.append({
                    "name": allergy['name'],
                    "type": "Allergy",
                    "date": allergy['recorded_date'],
                    "details": allergy
                })

        # Display active items
        for item in active_items:
            cols = st.columns([3, 1, 1])
            with cols[0]:
                with st.expander(item["name"]):
                    if item["type"] == "Condition":
                        st.write("Status:", item["details"]["clinical_status"])
                        st.write("Category:", ", ".join(item["details"]["category"]) if item["details"]["category"] else "Not specified")
                        st.write("Onset Date:", item["details"]["onset_date"])
                    elif item["type"] == "Medication":
                        st.write("Status:", item["details"]["status"])
                        st.write("Category:", item["details"]["category"])
                        st.write("Prescribed by:", item["details"]["prescriber"])
                        st.write("Prescribed Date:", item["details"]["authored_date"])
                        if item["details"]["reason"]:
                            st.write("Reason:", ", ".join(item["details"]["reason"]))
                    elif item["type"] == "Allergy":
                        st.write("Type:", item["details"]["type"])
                        st.write("Category:", ", ".join(item["details"]["category"]))
                        st.write("Criticality:", item["details"]["criticality"])
                        st.write("Status:", item["details"]["clinical_status"])
            cols[1].write(item["type"])
            cols[2].write(item["date"])

        # Historical section
        st.markdown(f"### Historical Items ({timeframe})")
        cols = st.columns([3, 1, 1])
        cols[0].markdown("**Item**")
        cols[1].markdown("**Type**")
        cols[2].markdown("**Date**")

        # Combine all historical items
        historical_items = []

        # Add historical conditions
        if historical_conditions is not None:
            for condition in historical_conditions:
                historical_items.append({
                    "name": condition['name'],
                    "type": "Condition",
                    "date": condition['abatement_date'] or condition['recorded_date'],
                    "details": condition
                })

        # Add historical medications
        if historical_meds is not None:
            for med in historical_meds:
                historical_items.append({
                    "name": med['medication'],
                    "type": "Medication",
                    "date": med['authored_date'],
                    "details": med
                })

        # Add reports
        if recent_reports is not None and older_reports is not None:
            for report in recent_reports + older_reports:
                historical_items.append({
                    "name": ", ".join(report['code']),
                    "type": "Report",
                    "date": report['effective_date'],
                    "details": report
                })

        # Sort historical items by date
        historical_items.sort(key=lambda x: x["date"] if x["date"] else "", reverse=True)

        # Display historical items
        for item in historical_items:
            cols = st.columns([3, 1, 1])
            with cols[0]:
                with st.expander(item["name"]):
                    if item["type"] == "Condition":
                        st.write("Status:", item["details"]["clinical_status"])
                        st.write("Category:", ", ".join(item["details"]["category"]) if item["details"]["category"] else "Not specified")
                        st.write("Onset Date:", item["details"]["onset_date"])
                        st.write("Resolved Date:", item["details"]["abatement_date"])
                    elif item["type"] == "Medication":
                        st.write("Status:", item["details"]["status"])
                        st.write("Category:", item["details"]["category"])
                        st.write("Prescribed by:", item["details"]["prescriber"])
                        st.write("Prescribed Date:", item["details"]["authored_date"])
                        if item["details"]["reason"]:
                            st.write("Reason:", ", ".join(item["details"]["reason"]))
                    elif item["type"] == "Report":
                        st.write("Status:", item["details"]["status"])
                        st.write("Category:", ", ".join(item["details"]["category"]))
                        st.write("Provider:", item["details"]["performer"])
                        st.write("Date:", item["details"]["effective_date"])
                        st.write("\nContent:")
                        st.write(item["details"]["content"])
            cols[1].write(item["type"])
            cols[2].write(item["date"])
        
    def generate_report(self, patient, patient_context, transcription, consultation_type):
        # Analyze transcribed text using Groq's LLM
        prompt = f"""This is a {consultation_type} consultation for this patient. Based on the transcription of the doctor-patient 
        consultation session below, write a report that includes the following sections:
        1. Patient information
        2. Prior conditions and pre-diagnosis
        3. Requested tests or medication to be prescribed

        Before the consultation transcription, here are active and historical allergies, 
        medications, conditions and medical reports of the patient that you need to take into account.
        
        Historical patient data:
        {patient_context}
        
        Transcription of the consultation session:
        {transcription}

        Give your response in the following markdown format:
        # Patient information:
        Name: {patient['name'][0]['given']} {patient['name'][0]['family']}
        Gender: {patient['gender']}
        Birth Date: {patient['birthDate']}
        [Pre-existing conditions, active and previous medications if any]
        
        # Allergies
        [Allergies if any]

        # Consultation summary:
        [Findings / complaints]

        # Pre-diagnosis:
        [pre-diagnosis]

        # Requested tests:
        - [test 1]
        - [test 2]
        - ...
        
        The final section should include either requested tests (if any) or a prescription if this is a follow-up consultation. 
        If not needed, the final section can be omitted.
        """

        completion = self.groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile", 
            temperature=0.7,
            max_tokens=2048,
        )
    
        return completion.choices[0].message.content

    def render_page(self):
        self.initialize_session_state()
        st.title("SageScript AI")

        # Get patient list
        search_requirements = st.session_state['search_requirements']
        if 'patients_result' not in st.session_state:
            st.session_state['patients_result'] = {'entry': []}

        patients_result = st.session_state['patients_result']
        if search_requirements is None:
            patients_result = self.fhir.search_resource('Patient', '')
        else:
            inputs = {}
            for r in search_requirements:
                inputs[r] = st.text_input(r)

            search = st.button('find patients')
            if search:
                patients_result = self.fhir.search_resource('Patient', inputs)
                if 'entry' not in patients_result or len(patients_result['entry']) == 0 or patients_result['entry'][0]['resource']['resourceType'] != 'Patient':
                    st.text('failed to find patient')
                    st.json(patients_result)
                    return
                st.session_state['patients_result'] = patients_result

        if len(patients_result['entry']) == 0:
            return

        # Top section with patient selection and context
        with st.container():
            col1, col2 = st.columns([1, 3])
            
            with col1:
                patient = st.selectbox(
                    label="Select Patient",
                    placeholder="Select Patient",
                    index=None if len(patients_result['entry']) > 1 else 0,
                    options=map(
                        lambda entry: entry['resource'],
                        patients_result['entry']
                    ),
                    format_func=lambda patient: f"{str.join(' ', patient['name'][0]['given'])} {patient['name'][0]['family']}"
                )

                # Reset state if patient selection changes
                if patient and ('patient_id' not in st.session_state or st.session_state['patient_id'] != patient['id']):
                    st.session_state['patient_id'] = patient['id']
                    self.reset_session_state()
                
            with col2:
                if patient:
                    time_range, context_types, consultation_type = self.create_context_selectors()

        if patient:
            # Audio recording section
            st.subheader("Voice Input")
            
            # Create two columns for record and upload options
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Record Consultation**")
                audio_value = st.audio_input("Record your consultation notes")
                if audio_value is not None and not st.session_state['audio_processed']:
                    st.session_state['audio_value'] = audio_value
                    st.session_state['audio_source'] = 'recorded'
            
            with col2:
                st.markdown("**Upload Audio File**")
                uploaded_file = st.file_uploader("Upload consultation audio", type=['mp3', 'wav', 'm4a'])
                if uploaded_file is not None and not st.session_state['audio_processed']:
                    st.session_state['audio_value'] = uploaded_file
                    st.session_state['audio_source'] = 'uploaded'

            # Process button
            col1, col2 = st.columns(2)
            with col1:
                process_disabled = 'audio_value' not in st.session_state
                if st.button("Process Consultation", type="primary", disabled=process_disabled):
                    with st.spinner("Processing..."):
                        # Process audio if available
                        if 'audio_value' in st.session_state and not st.session_state['audio_processed']:
                            transcription = self.process_audio(st.session_state['audio_value'])
                            st.session_state['transcription'] = transcription
                            st.session_state['audio_processed'] = True
                        
                        # Get patient context
                        patient_context = self.get_patient_context(patient["id"], time_range, context_types)
                        st.session_state['patient_context'] = patient_context
                        
                        # Generate report if transcription exists
                        if st.session_state['transcription']:
                            report = self.generate_report(
                                patient, 
                                st.session_state['patient_context'],
                                st.session_state['transcription'],
                                consultation_type
                            )
                            st.session_state['editable_report'] = report
                        
                    st.success("Processing complete!")

            with col2:
                if st.button("Reset"):
                    self.reset_session_state()
                    st.rerun()

            # Tabs for transcription and report
            tab1, tab2, tab3 = st.tabs(["Transcription", "Report", "Patient History"])
            
            with tab1:
                if st.session_state['transcription']:
                    st.text_area("", st.session_state['transcription'], height=400)
                else:
                    st.info("No transcription available yet. Start recording to see the transcription here.")


            with tab2:
                if st.session_state['editable_report'] != "No consultation recorded yet":
                    edited_report = st.text_area(
                        "",
                        value=st.session_state['editable_report'],
                        height=400,
                        key="report_editor"
                    )
                    st.session_state['editable_report'] = edited_report

                    # Export options
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("Submit report"):
                            txt_content = edited_report.encode('utf-8')
                            current_date = datetime.now().strftime("%Y%m%d")
                            filename = f"consultation_report_{current_date}.txt"
                
                    with col2:
                        from reportlab.lib.pagesizes import letter
                        from reportlab.platypus import SimpleDocTemplate, Paragraph
                        from reportlab.lib.styles import getSampleStyleSheet
                        import io
                        
                        # Create in-memory PDF
                        buffer = io.BytesIO()
                        doc = SimpleDocTemplate(buffer, pagesize=letter)
                        styles = getSampleStyleSheet()
                        
                        # Convert report content to PDF
                        content = []
                        for line in edited_report.split('\n'):
                            if line.strip():  # Skip empty lines
                                content.append(Paragraph(line, styles['Normal']))
                        
                        doc.build(content)
                        
                        # Prepare download button
                        current_date = datetime.now().strftime("%Y%m%d")
                        pdf_filename = f"consultation_report_{current_date}.pdf"
                        
                        st.download_button(
                            label="Save as PDF",
                            data=buffer.getvalue(),
                            file_name=pdf_filename,
                            mime="application/pdf"
                        )
                else:
                    st.info("No consultation recorded yet. Record and process consultation to generate a report.")
            with tab3:
                if patient:
                    self.display_patient_history(patient["id"], time_range, context_types)
                else:
                    st.info("Select a patient to view their history.")

if 'token' not in st.session_state:
    st.switch_page('main.py')
else:
    App().render_page()