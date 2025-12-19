from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

app = FastAPI(
    title="Academic Communication Service",
    description="Handles Emails and Dashboard Notifications for Students and Faculty.",
    version="1.1"
)

# --- SMTP CONFIGURATION (SECURE) ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Retrieve from environment variables, or use provided defaults for testing
SENDER_EMAIL = os.getenv("SMTP_USER", "sjsvardhan@gmail.com")
SENDER_PASSWORD = os.getenv("SMTP_PASS", "kpke ekfk fqhz cqge") # Ensure this is an App Password if using Gmail

if not SENDER_EMAIL or not SENDER_PASSWORD:
    raise RuntimeError("SMTP credentials not found. Please set SMTP_USER and SMTP_PASS environment variables.")

# --- PYDANTIC MODELS ---

class CourseCreationNotify(BaseModel):
    course_name: str
    semester: str
    student_emails: List[EmailStr]

class FacultyAssignmentNotify(BaseModel):
    faculty_id: str
    faculty_email: EmailStr
    faculty_name: str
    subject_name: str
    students: List[Dict[str, str]] = []  # List of {name, email, roll_number}

class StudentEnrollmentNotify(BaseModel):
    student_id: str
    student_name: str
    student_email: EmailStr
    subject_name: str
    faculty_id: str
    faculty_email: EmailStr

class ResultReleaseNotify(BaseModel):
    exam_name: str
    student_list: List[Dict[str, str]]  # {email, id}

class StudentDetentionNotify(BaseModel):
    student_id: str
    student_name: str
    student_email: EmailStr
    reason: str = "Academic Performance / Attendance Shortage"

class StudentCreditShortageNotify(BaseModel):
    student_id: str
    student_name: str
    student_email: EmailStr
    current_credits: float = 0.0
    required_credits: float = 0.0

class EventNotify(BaseModel):
    event_name: str
    update_type: str # CANCELLED or RESCHEDULED
    details: str
    recipient_list: List[EmailStr]

# --- EMAIL UTILITY ---

async def send_email_async(to_email: str, subject: str, body: str, html_body: str = None):
    print(f"DEBUG START: Sending mail to {to_email}...")
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        
        if html_body:
            msg.attach(MIMEText(html_body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))

        print(f"DEBUG: Connecting to {SMTP_SERVER}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20)
        # server.set_debuglevel(1)  # Enables detailed SMTP transaction logs
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()

        print(f"SUCCESS: Email sent to {to_email}")
        return True

    except Exception as e:
        print(f"CRITICAL ERROR in send_email_async: {type(e).__name__} - {e}")
        return False

# --- INTERNAL NOTIFICATION (DB PLACEHOLDER) ---

async def save_notification_to_db(user_id: str, title: str, message: str, category: str):
    notification_data = {
        "title": title,
        "message": message,
        "category": category,
        "timestamp": datetime.utcnow().isoformat(),
        "is_read": False
    }
    print(f"Notification saved for {user_id}: {title}")

# --- API ENDPOINTS ---

@app.post("/api/v1/notify/course-creation")
async def notify_course_creation(data: CourseCreationNotify, background_tasks: BackgroundTasks):

    subject = f"New Courses Available – {data.semester}"
    body = (
        f"Hello Student,\n\n"
        f"New courses for {data.semester} have been released.\n"
        f"Course: {data.course_name}\n\n"
        f"Please login to AcademixAI to register."
    )

    for email in data.student_emails:
        background_tasks.add_task(send_email_async, email, subject, body)
        background_tasks.add_task(
            save_notification_to_db,
            "student_id_placeholder",
            "Course Registration Open",
            body,
            "ACADEMIC"
        )

    return {"status": "SUCCESS", "message": "Course notifications queued."}


@app.post("/api/v1/notify/faculty-assignment")
async def notify_faculty_assignment(data: FacultyAssignmentNotify, background_tasks: BackgroundTasks):
    print(f"DEBUG: notify_faculty_assignment received for faculty {data.faculty_email} with {len(data.students)} students")
    
    student_list_text = ""
    if data.students:
        student_list_text = "\n\nEnrolled Students List:\n" + "\n".join(
            [f"- {s.get('name')} ({s.get('roll_number')})" for s in data.students]
        )

    subject = "New Teaching Assignment"
    body = (
        f"Hello Prof. {data.faculty_name},\n\n"
        f"You have been assigned to teach:\n"
        f"Subject: {data.subject_name}\n"
        f"{student_list_text}\n"
        f"\nPlease check your dashboard for more details."
    )

    print(f"DEBUG: Queuing email to Faculty: {data.faculty_email}")
    background_tasks.add_task(send_email_async, data.faculty_email, subject, body)
    
    # Notify each Student in the list
    if data.students:
        for student in data.students:
            s_email = student.get("email")
            if s_email:
                print(f"DEBUG: Queuing email to Student: {s_email}")
                student_subject = f"Faculty Assigned for {data.subject_name}"
                student_body = (
                    f"Hello {student.get('name')},\n\n"
                    f"Prof. {data.faculty_name} has been assigned to teach your course: {data.subject_name}.\n\n"
                    f"Regards,\nAcademixAI Team"
                )
                background_tasks.add_task(send_email_async, s_email, student_subject, student_body)

    background_tasks.add_task(
        save_notification_to_db,
        data.faculty_id,
        "New Teaching Assignment",
        body,
        "FACULTY"
    )

    return {"status": "SUCCESS", "message": "Faculty and students notified."}


@app.post("/api/v1/notify/student-enrollment")
async def notify_student_enrollment(data: StudentEnrollmentNotify, background_tasks: BackgroundTasks):

    # Notify Faculty (if info available)
    if data.faculty_email:
        fac_subject = f"New Enrollment – {data.subject_name}"
        fac_body = (
            f"Hello,\n\n"
            f"A student has enrolled in your subject: {data.subject_name}.\n"
            f"Student: {data.student_name} ({data.student_id})\n\n"
            f"Regards,\nAcademixAI Team"
        )
        background_tasks.add_task(send_email_async, data.faculty_email, fac_subject, fac_body)
        background_tasks.add_task(
            save_notification_to_db,
            data.faculty_id,
            "New Student Enrollment",
            fac_body,
            "ENROLLMENT"
        )

    # Notify Student
    if data.student_email:
        stu_subject = f"Enrolled Successfully: {data.subject_name}"
        stu_body = (
            f"Hello {data.student_name},\n\n"
            f"You have been successfully enrolled in the course: {data.subject_name} for this semester.\n"
            f"You can now access the course materials and syllabus on your dashboard.\n\n"
            f"Best wishes,\nAcademixAI Team"
        )
        background_tasks.add_task(send_email_async, data.student_email, stu_subject, stu_body)
        background_tasks.add_task(
            save_notification_to_db,
            data.student_id,
            "Course Enrollment Confirmation",
            stu_body,
            "ENROLLMENT"
        )

    return {"status": "SUCCESS", "message": "Enrollment notifications queued."}


@app.post("/api/v1/notify/results-release")
async def notify_results_release(data: ResultReleaseNotify, background_tasks: BackgroundTasks):

    subject = f"Results Released – {data.exam_name}"
    body = (
        f"Dear Student,\n\n"
        f"Results for {data.exam_name} have been published.\n"
        f"Please login to AcademixAI to view your grades."
    )

    for student in data.student_list:
        background_tasks.add_task(send_email_async, student["email"], subject, body)
        background_tasks.add_task(
            save_notification_to_db,
            student["id"],
            "Results Published",
            body,
            "EXAM"
        )

    return {"status": "SUCCESS", "message": "Result notifications queued."}


@app.post("/api/v1/notify/student-detention")
async def notify_student_detention(data: StudentDetentionNotify, background_tasks: BackgroundTasks):
    subject = "URGENT: Academic Status Update - DETAINED"
    
    html_body = f"""
    <html>
    <body style="font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f1115; margin: 0; padding: 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0f1115; padding: 40px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color: #1a1d23; border-radius: 24px; overflow: hidden; border: 1px solid rgba(255,255,255,0.05);">
                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); padding: 50px 40px; text-align: center;">
                                <div style="display: inline-block; padding: 12px; background: rgba(255,255,255,0.1); border-radius: 12px; margin-bottom: 20px;">
                                    <span style="color: #ffffff; font-size: 32px; font-weight: 800; letter-spacing: -1px;">ACADEMIX AI</span>
                                </div>
                                <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;">Status Update</h1>
                            </td>
                        </tr>
                        <!-- Body -->
                        <tr>
                            <td style="padding: 40px;">
                                <div style="background: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; padding: 20px; border-radius: 12px; margin-bottom: 30px;">
                                    <h2 style="color: #ef4444; margin: 0 0 5px 0; font-size: 18px; font-weight: 700;">DUE TO ACADEMIC IRREGULARITY</h2>
                                    <p style="color: #cbd5e1; margin: 0; font-size: 14px;">Your status has been updated to <strong>DETAINED</strong></p>
                                </div>

                                <p style="color: #94a3b8; line-height: 1.6; margin-bottom: 25px; font-size: 16px;">
                                    Dear <strong>{data.student_name}</strong>,<br><br>
                                    Following a comprehensive review of your records, the Office of Administration has issued a mandatory <strong>Detention Order</strong>.
                                </p>
                                
                                <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); padding: 25px; border-radius: 16px; margin-bottom: 30px;">
                                    <p style="color: #e2e8f0; margin: 0; font-weight: 600; margin-bottom: 15px; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">Official Reason:</p>
                                    <p style="color: #94a3b8; margin: 0; line-height: 1.6; font-style: italic;">"{data.reason}"</p>
                                </div>

                                <div style="background: #ef4444; padding: 2px; border-radius: 12px;">
                                    <div style="background: #1a1d23; padding: 20px; border-radius: 10px;">
                                        <p style="color: #ffffff; margin: 0; font-weight: 700; margin-bottom: 10px;">CONSEQUENCES:</p>
                                        <ul style="color: #94a3b8; margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.8;">
                                            <li>Examination eligibility revoked indefinitely.</li>
                                            <li>Access to course registration portals locked.</li>
                                            <li>Restricted access to specific campus digital resources.</li>
                                        </ul>
                                    </div>
                                </div>

                                <p style="color: #94a3b8; line-height: 1.6; margin-top: 30px; font-size: 14px;">
                                    <strong>Required Action:</strong> Report to the Academic Cell within 24 hours to clarify your standing.
                                </p>
                            </td>
                        </tr>
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #111418; padding: 30px; text-align: center; border-top: 1px solid rgba(255,255,255,0.05);">
                                <p style="color: #64748b; font-size: 13px; margin: 0;">&copy; 2024 AcademixAI Unified Systems &bull; Administration Module</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    plain_body = f"URGENT: Your academic status has been updated to DETAINED. Reason: {data.reason}. Please report to the administration cell immediately."
    
    background_tasks.add_task(send_email_async, data.student_email, subject, plain_body, html_body)
    
    background_tasks.add_task(
        save_notification_to_db,
        data.student_id,
        "Status Update: DETAINED",
        f"Academic status changed to DETAINED. Reason: {data.reason}",
        "ADMIN_ALERT"
    )

    return {"status": "SUCCESS", "message": "Detention notification queued."}

@app.post("/api/v1/notify/student-credit-shortage")
async def notify_student_credit_shortage(data: StudentCreditShortageNotify, background_tasks: BackgroundTasks):
    subject = "Academic Warning: Credit Shortage Detected"
    
    html_body = f"""
    <html>
    <body style="font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f1115; margin: 0; padding: 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0f1115; padding: 40px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color: #1a1d23; border-radius: 24px; overflow: hidden; border: 1px solid rgba(255,255,255,0.05);">
                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 50px 40px; text-align: center;">
                                <div style="display: inline-block; padding: 12px; background: rgba(255,255,255,0.1); border-radius: 12px; margin-bottom: 20px;">
                                    <span style="color: #ffffff; font-size: 32px; font-weight: 800; letter-spacing: -1px;">ACADEMIX AI</span>
                                </div>
                                <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;">Credit Alert</h1>
                            </td>
                        </tr>
                        <!-- Body -->
                        <tr>
                            <td style="padding: 40px;">
                                <div style="background: rgba(245, 158, 11, 0.1); border-left: 4px solid #f59e0b; padding: 20px; border-radius: 12px; margin-bottom: 30px;">
                                    <h2 style="color: #f59e0b; margin: 0 0 5px 0; font-size: 18px; font-weight: 700;">PROMOTION ELIGIBILITY RISK</h2>
                                    <p style="color: #cbd5e1; margin: 0; font-size: 14px;">Credit shortage detected in your academic profile.</p>
                                </div>

                                <p style="color: #94a3b8; line-height: 1.6; margin-bottom: 25px; font-size: 16px;">
                                    Dear <strong>{data.student_name}</strong>,<br><br>
                                    Our automated performance tracking system has flagged a potential risk regarding your promotion to the next academic year.
                                </p>
                                
                                <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); padding: 25px; border-radius: 16px; margin-bottom: 30px;">
                                    <table width="100%" cellpadding="0" cellspacing="0">
                                        <tr>
                                            <td style="color: #e2e8f0; font-weight: 600; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">Current Credits:</td>
                                            <td style="color: #f59e0b; font-weight: 800; text-align: right; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">{data.current_credits}</td>
                                        </tr>
                                        <tr>
                                            <td style="color: #e2e8f0; font-weight: 600; padding: 10px 0;">Required for Promotion:</td>
                                            <td style="color: #ffffff; font-weight: 800; text-align: right; padding: 10px 0;">{data.required_credits}</td>
                                        </tr>
                                    </table>
                                </div>

                                <div style="background: rgba(255,255,255,0.02); border-left: 4px solid #64748b; padding: 20px; border-radius: 8px;">
                                    <p style="color: #ffffff; margin: 0; font-weight: 700; margin-bottom: 15px; font-size: 14px; text-transform: uppercase;">Required Next Steps:</p>
                                    <ul style="color: #94a3b8; margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.8;">
                                        <li>Verify all subject results on the Student Dashboard.</li>
                                        <li>Apply for immediate supplementary exams (if available).</li>
                                        <li>Schedule a consultation with your Faculty Advisor.</li>
                                    </ul>
                                </div>

                                <p style="color: #64748b; font-size: 12px; margin-top: 30px; font-style: italic;">
                                    Note: Failure to reach the required credit threshold may result in academic detention according to University regulations.
                                </p>
                            </td>
                        </tr>
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #111418; padding: 30px; text-align: center; border-top: 1px solid rgba(255,255,255,0.05);">
                                <p style="color: #64748b; font-size: 13px; margin: 0;">&copy; 2024 AcademixAI Unified Systems &bull; Academic Surveillance</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    plain_body = f"ACADEMIC ALERT: Credit shortage detected ({data.current_credits}/{data.required_credits}). You are at risk of detention. Please check the portal immediately."

    background_tasks.add_task(send_email_async, data.student_email, subject, plain_body, html_body)
    
    background_tasks.add_task(
        save_notification_to_db,
        data.student_id,
        "Status Warning: Credit Shortage",
        f"Credit Shortage detected ({data.current_credits}/{data.required_credits}). Risk of detention.",
        "ACADEMIC_ALERT"
    )

    return {"status": "SUCCESS", "message": "Credit shortage notification queued."}


@app.post("/api/v1/notify/event-update")
async def notify_event_update(data: EventNotify, background_tasks: BackgroundTasks):
    """Specific endpoint for Club Event updates with God Tier aesthetic."""
    subject = f"URGENT: {data.event_name} Update"
    
    # Dynamic Colors
    is_cancelled = data.update_type == "CANCELLED"
    accent_color = "#ef4444" if is_cancelled else "#6366f1"
    secondary_accent = "#991b1b" if is_cancelled else "#4338ca"
    bg_gradient = f"linear-gradient(135deg, {accent_color} 0%, {secondary_accent} 100%)"
    
    html_content = f"""
    <html>
    <body style="font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f1115; margin: 0; padding: 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #0f1115; padding: 40px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color: #1a1d23; border-radius: 32px; overflow: hidden; border: 1px solid rgba(255,255,255,0.05); box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);">
                        <!-- Header -->
                        <tr>
                            <td style="background: {bg_gradient}; padding: 60px 40px; text-align: center;">
                                <div style="display: inline-block; padding: 12px 20px; background: rgba(255,255,255,0.1); border-radius: 100px; margin-bottom: 24px; border: 1px solid rgba(255,255,255,0.2);">
                                    <span style="color: #ffffff; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 2px;">Unified Campus Protocol</span>
                                </div>
                                <h1 style="color: #ffffff; margin: 0; font-size: 32px; font-weight: 800; letter-spacing: -1px; line-height: 1.2;">{data.event_name}</h1>
                                <p style="color: rgba(255,255,255,0.8); margin: 12px 0 0 0; font-size: 16px; font-weight: 500;">Status: <span style="color: #ffffff; font-weight: 700;">{data.update_type}</span></p>
                            </td>
                        </tr>
                        <!-- Content -->
                        <tr>
                            <td style="padding: 50px 40px;">
                                <h2 style="color: #ffffff; margin: 0 0 20px 0; font-size: 20px; font-weight: 700;">Important Notification</h2>
                                <p style="color: #94a3b8; line-height: 1.8; margin-bottom: 30px; font-size: 16px;">
                                    Dear Participant,<br><br>
                                    This is an official update regarding your registration for <strong>{data.event_name}</strong>. 
                                    Please review the detailed changes below to ensure your schedule remains synchronised.
                                </p>
                                
                                <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); padding: 30px; border-radius: 24px; margin-bottom: 30px;">
                                    <h4 style="color: #e2e8f0; margin: 0 0 15px 0; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; font-weight: 700;">Adjustment Log:</h4>
                                    <p style="color: #cbd5e1; margin: 0; line-height: 1.6; font-size: 15px;">{data.details}</p>
                                </div>

                                <div style="text-align: center; margin-top: 20px;">
                                    <p style="color: #64748b; font-size: 14px;">Please update your calendars accordingly.</p>
                                </div>
                            </td>
                        </tr>
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #111418; padding: 40px; text-align: center; border-top: 1px solid rgba(255,255,255,0.05);">
                                <div style="margin-bottom: 20px;">
                                    <span style="color: #ffffff; font-size: 18px; font-weight: 800; letter-spacing: -0.5px;">ACADEMIX AI</span>
                                </div>
                                <p style="color: #475569; font-size: 13px; margin: 0; line-height: 1.5;">
                                    &copy; 2024 Unified Academic Systems. All records encrypted.<br>
                                    This is an automated priority dispatch. Do not reply.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    plain_body = f"URGENT: {data.event_name} has been {data.update_type}.\nDetails: {data.details}\nPlease check the portal for more info."
    
    for email in data.recipient_list:
        background_tasks.add_task(send_email_async, email, subject, plain_body, html_content)
        
    return {"status": "SUCCESS", "message": f"Alerts sent for {data.event_name}."}

@app.get("/api/v1/status")
def health_check():
    return {"status": "SUCCESS", "uptime": "normal", "service": "Notification Engine"}
