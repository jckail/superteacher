import random
from typing import List
from .database import Student, Class, Section

def generate_name():
    first_names = ["James", "Emma", "Liam", "Olivia", "Noah", "Ava", "William", "Sophia", "Mason", "Isabella",
                  "Ethan", "Mia", "Michael", "Charlotte", "Alexander", "Amelia", "Daniel", "Harper", "Matthew",
                  "Evelyn", "Aiden", "Abigail", "Henry", "Emily", "Joseph", "Elizabeth", "Jackson", "Sofia",
                  "Sebastian", "Avery", "David", "Ella", "Carter", "Scarlett", "Owen", "Grace", "Wyatt", "Victoria"]
    
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez",
                  "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore",
                  "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez",
                  "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen"]
    
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def generate_attendance():
    # More varied attendance patterns
    attendance_profiles = [
        (0.98, 1.00),    # Perfect/Near perfect (5% chance)
        (0.90, 0.97),    # Excellent (15% chance)
        (0.80, 0.89),    # Good (40% chance)
        (0.70, 0.79),    # Fair (25% chance)
        (0.50, 0.69),    # Poor (10% chance)
        (0.30, 0.49)     # Very Poor (5% chance)
    ]
    
    weights = [5, 15, 40, 25, 10, 5]
    profile = random.choices(attendance_profiles, weights=weights)[0]
    
    total_days = random.randint(150, 180)
    attendance_rate = random.uniform(profile[0], profile[1])
    attended_days = int(total_days * attendance_rate)
    percentage = round(attendance_rate * 100, 1)
    
    return f"{attended_days}/{total_days}", percentage

def generate_homework_data():
    # More varied homework completion rates
    completion_profiles = [
        (0.95, 1.00),    # Perfect/Near perfect
        (0.85, 0.94),    # Excellent
        (0.70, 0.84),    # Good
        (0.50, 0.69),    # Fair
        (0.30, 0.49),    # Poor
        (0.10, 0.29)     # Very Poor
    ]
    
    weights = [5, 15, 35, 25, 15, 5]
    profile = random.choices(completion_profiles, weights=weights)[0]
    
    total = random.randint(40, 60)
    completion_rate = random.uniform(profile[0], profile[1])
    completed = int(total * completion_rate)
    
    # Quality of completed work varies
    quality_factor = random.uniform(0.6, 1.0)
    points = int(completed * 10 * quality_factor)
    
    return f"{completed}/{total}", points

def generate_test_scores(num_tests):
    tests = {}
    subjects = [
        "Midterm", "Final", "Quiz", "Project", "Essay", "Lab Report", 
        "Presentation", "Research Paper", "Group Project", "Portfolio",
        "Case Study", "Practical Exam", "Oral Exam", "Written Assignment"
    ]
    
    # Performance profiles (min%, max%)
    profiles = [
        (95, 100),  # Outstanding
        (85, 94),   # Excellent
        (75, 84),   # Good
        (65, 74),   # Fair
        (55, 64),   # Poor
        (35, 54)    # Struggling
    ]
    
    # Select a primary performance profile for this student
    weights = [5, 15, 35, 25, 15, 5]
    primary_profile = random.choices(profiles, weights=weights)[0]
    
    for _ in range(num_tests):
        test_name = random.choice(subjects)
        
        # 80% chance to use primary profile, 20% chance for variation
        if random.random() < 0.8:
            score_range = primary_profile
        else:
            # Pick a different profile for variety
            score_range = random.choice([p for p in profiles if p != primary_profile])
        
        score = random.randint(score_range[0], score_range[1])
        tests[f"{test_name} {random.randint(1,3)}"] = f"{score}%"
    
    return tests

def calculate_gpa(test_scores):
    scores = [int(score.rstrip('%')) for score in test_scores.values()]
    avg_score = sum(scores) / len(scores)
    return round(avg_score / 25, 1)  # Convert percentage to 4.0 scale

def generate_ai_insights(gpa, attendance_percentage, homework_completed_ratio):
    # Parse homework completion ratio
    completed, total = map(int, homework_completed_ratio.split('/'))
    homework_rate = completed / total

    # Complex status determination based on multiple factors
    status_factors = {
        "Academic": gpa / 4.0,  # Normalized to 0-1
        "Attendance": attendance_percentage / 100,
        "Homework": homework_rate
    }
    
    # Calculate overall performance score
    performance_score = (status_factors["Academic"] * 0.5 + 
                        status_factors["Attendance"] * 0.25 + 
                        status_factors["Homework"] * 0.25)
    
    # Determine status
    if performance_score >= 0.9:
        status = "Outstanding"
    elif performance_score >= 0.8:
        status = "Excellent"
    elif performance_score >= 0.7:
        status = "Good"
    elif performance_score >= 0.6:
        status = "Fair"
    elif performance_score >= 0.5:
        status = "Needs Improvement"
    else:
        status = "At Risk"

    # Generate detailed recommendations based on specific factors
    recommendations = []
    
    # Academic-specific recommendations
    if status_factors["Academic"] < 0.6:
        recommendations.extend([
            "Schedule regular tutoring sessions",
            "Focus on foundational concepts",
            "Develop better study techniques",
            "Consider study groups for difficult subjects",
            "Meet with teachers for extra help"
        ])
    elif status_factors["Academic"] < 0.75:
        recommendations.extend([
            "Review challenging topics regularly",
            "Participate more in class discussions",
            "Seek clarification on difficult concepts",
            "Practice active learning techniques"
        ])
    else:
        recommendations.extend([
            "Consider advanced placement courses",
            "Explore academic competitions",
            "Mentor other students",
            "Pursue independent study projects"
        ])

    # Attendance-specific recommendations
    if status_factors["Attendance"] < 0.8:
        recommendations.extend([
            "Develop better time management",
            "Address transportation issues if any",
            "Create morning routine for punctuality",
            "Schedule medical appointments after school"
        ])

    # Homework-specific recommendations
    if status_factors["Homework"] < 0.7:
        recommendations.extend([
            "Create homework schedule",
            "Use planner to track assignments",
            "Find quiet study space",
            "Break large assignments into smaller tasks",
            "Join after-school homework club"
        ])

    # Select 2-3 most relevant recommendations
    final_recommendations = random.sample(recommendations, min(len(recommendations), random.randint(2, 3)))
    
    return {
        "status": status,
        "recommendation": " | ".join(final_recommendations),
        "performance_breakdown": {
            "academic_strength": f"{status_factors['Academic']*100:.1f}%",
            "attendance_impact": f"{status_factors['Attendance']*100:.1f}%",
            "homework_consistency": f"{status_factors['Homework']*100:.1f}%"
        }
    }

def create_sample_data(db):
    """Create sample classes, sections, and students"""
    
    # Add classes
    classes = [
        {"id": "C101", "name": "Mathematics"},
        {"id": "C102", "name": "Science"},
        {"id": "C103", "name": "English"},
        {"id": "C104", "name": "History"},
        {"id": "C105", "name": "Literature"},
        {"id": "C106", "name": "Physics"},
        {"id": "C107", "name": "Biology"},
        {"id": "C108", "name": "Chemistry"},
        {"id": "C109", "name": "Computer Science"},
        {"id": "C110", "name": "Art"},
        {"id": "C111", "name": "Music"}
    ]
    
    for class_data in classes:
        db.add(Class(**class_data))
    db.commit()
    
    # Add sections for each class
    all_classes = db.query(Class).all()
    for class_obj in all_classes:
        for section in ['A', 'B', 'C']:
            db.add(Section(name=section, class_id=class_obj.id))
    db.commit()
    
    # Create 50 students
    for i in range(30):
        # Basic info
        name = generate_name()
        grade = random.randint(9, 12)
        class_obj = random.choice(all_classes)
        section = random.choice(['A', 'B', 'C'])
        
        # Generate test scores and calculate GPA
        test_scores = generate_test_scores(random.randint(6, 12))
        gpa = calculate_gpa(test_scores)
        
        # Generate attendance data
        attendance_days, attendance_percentage = generate_attendance()
        
        # Generate homework data
        homework_completed, homework_points = generate_homework_data()
        
        # Academic performance
        academic_performance = {
            "rank": "Top 5%" if gpa >= 3.7 else "Top 10%" if gpa >= 3.3 else "Top 25%" if gpa >= 3.0 else "Average",
            "tests": test_scores,
            "homework": generate_test_scores(random.randint(4, 8))  # Different homework assignments
        }
        
        # AI insights with more detailed analysis
        ai_insights = generate_ai_insights(gpa, attendance_percentage, homework_completed)
        
        # Create student
        student = Student(
            id=f"ST{i+1:04d}",
            name=name,
            grade=grade,
            class_id=class_obj.id,
            section=section,
            gpa=gpa,
            attendance_percentage=attendance_percentage,
            attendance_days=attendance_days,
            homework_points=homework_points,
            homework_completed=homework_completed,
            academic_performance=academic_performance,
            ai_insights=ai_insights
        )
        
        db.add(student)
    
    db.commit()
