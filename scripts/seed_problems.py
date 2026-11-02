import asyncio
from uuid import uuid4

from sqlalchemy import select

from medicode.db.session import AsyncSessionLocal
from medicode.models.academic import Course, CourseOffering, Department, OfferingStatus
from medicode.models.content import Experiment, Lab, Problem, TestCase


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        # 1. Ensure seed department exists
        dept = await session.scalar(select(Department).where(Department.code == "CS"))
        if dept is None:
            dept = Department(name="Computer Science & Engineering", code="CS")
            session.add(dept)
            await session.flush()

        # 2. Ensure course exists
        course = await session.scalar(select(Course).where(Course.code == "CS101"))
        if course is None:
            course = Course(
                department_id=dept.id,
                title="Python Programming & Problem Solving",
                code="CS101",
                credits=4,
            )
            session.add(course)
            await session.flush()

        # 3. Ensure lab exists
        lab = await session.scalar(select(Lab).where(Lab.course_id == course.id, Lab.title == "Week 1: Fundamentals"))
        if lab is None:
            lab = Lab(
                course_id=course.id,
                title="Week 1: Fundamentals",
                description="Fundamental Python input, output, and algorithmic operations.",
                sort_order=1,
                is_published=True,
            )
            session.add(lab)
            await session.flush()

        # 4. Ensure experiment exists
        experiment = await session.scalar(select(Experiment).where(Experiment.lab_id == lab.id))
        if experiment is None:
            experiment = Experiment(
                lab_id=lab.id,
                title="Basic Syntax & Data Structures",
                description="Core arithmetic, string manipulation, and standard I/O.",
                sort_order=1,
                is_published=True,
            )
            session.add(experiment)
            await session.flush()

        # 5. Problem 1: Sum of Two Numbers
        p1 = await session.scalar(select(Problem).where(Problem.title == "Sum of Two Numbers"))
        if p1 is None:
            p1 = Problem(
                experiment_id=experiment.id,
                title="Sum of Two Numbers",
                statement=(
                    "Read two space-separated integers `a` and `b` from standard input.\n"
                    "Compute and print their arithmetic sum.\n\n"
                    "**Example Input:**\n`2 3`\n\n"
                    "**Example Output:**\n`5`"
                ),
                difficulty="EASY",
                time_limit_ms=1000,
                memory_limit_mb=128,
                comparison_mode="ignore_whitespace",
                is_published=True,
            )
            session.add(p1)
            await session.flush()

            # Test cases for Problem 1 (Visible sample + Hidden)
            tcs_p1 = [
                TestCase(
                    problem_id=p1.id,
                    input_data="2 3\n",
                    expected_output="5\n",
                    is_hidden=False,
                    points=10,
                    sort_order=1,
                ),
                TestCase(
                    problem_id=p1.id,
                    input_data="10 -4\n",
                    expected_output="6\n",
                    is_hidden=False,
                    points=10,
                    sort_order=2,
                ),
                TestCase(
                    problem_id=p1.id,
                    input_data="0 0\n",
                    expected_output="0\n",
                    is_hidden=True,
                    points=20,
                    sort_order=3,
                ),
                TestCase(
                    problem_id=p1.id,
                    input_data="-50 -50\n",
                    expected_output="-100\n",
                    is_hidden=True,
                    points=20,
                    sort_order=4,
                ),
                TestCase(
                    problem_id=p1.id,
                    input_data="1000000000 2000000000\n",
                    expected_output="3000000000\n",
                    is_hidden=True,
                    points=40,
                    sort_order=5,
                ),
            ]
            session.add_all(tcs_p1)
            print(f"Created Problem 1: 'Sum of Two Numbers' (ID: {p1.id}) with 5 test cases.")
        else:
            print(f"Problem 1 already exists (ID: {p1.id}).")

        # 6. Problem 2: Reverse a String
        p2 = await session.scalar(select(Problem).where(Problem.title == "Reverse a String"))
        if p2 is None:
            p2 = Problem(
                experiment_id=experiment.id,
                title="Reverse a String",
                statement=(
                    "Read a single line of string from standard input.\n"
                    "Print the reversed string.\n\n"
                    "**Example Input:**\n`hello`\n\n"
                    "**Example Output:**\n`olleh`"
                ),
                difficulty="EASY",
                time_limit_ms=1000,
                memory_limit_mb=128,
                comparison_mode="ignore_whitespace",
                is_published=True,
            )
            session.add(p2)
            await session.flush()

            # Test cases for Problem 2 (Visible sample + Hidden)
            tcs_p2 = [
                TestCase(
                    problem_id=p2.id,
                    input_data="hello\n",
                    expected_output="olleh\n",
                    is_hidden=False,
                    points=25,
                    sort_order=1,
                ),
                TestCase(
                    problem_id=p2.id,
                    input_data="racecar\n",
                    expected_output="racecar\n",
                    is_hidden=False,
                    points=25,
                    sort_order=2,
                ),
                TestCase(
                    problem_id=p2.id,
                    input_data="MediCode Sandbox\n",
                    expected_output="xobdnaS edoCideM\n",
                    is_hidden=True,
                    points=25,
                    sort_order=3,
                ),
                TestCase(
                    problem_id=p2.id,
                    input_data="123456789!\n",
                    expected_output="!987654321\n",
                    is_hidden=True,
                    points=25,
                    sort_order=4,
                ),
            ]
            session.add_all(tcs_p2)
            print(f"Created Problem 2: 'Reverse a String' (ID: {p2.id}) with 4 test cases.")
        else:
            print(f"Problem 2 already exists (ID: {p2.id}).")

        # 7. Problem 3: Factorial of a Number
        p3 = await session.scalar(select(Problem).where(Problem.title == "Factorial of a Number"))
        if p3 is None:
            p3 = Problem(
                experiment_id=experiment.id,
                title="Factorial of a Number",
                statement=(
                    "Read a non-negative integer `n` from standard input.\n"
                    "Calculate and print its factorial `n!` (where `0! = 1`).\n\n"
                    "**Example Input:**\n`5`\n\n"
                    "**Example Output:**\n`120`"
                ),
                difficulty="EASY",
                time_limit_ms=1000,
                memory_limit_mb=128,
                comparison_mode="ignore_whitespace",
                is_published=True,
            )
            session.add(p3)
            await session.flush()

            # Test cases for Problem 3 (Visible sample + Hidden)
            tcs_p3 = [
                TestCase(
                    problem_id=p3.id,
                    input_data="0\n",
                    expected_output="1\n",
                    is_hidden=False,
                    points=20,
                    sort_order=1,
                ),
                TestCase(
                    problem_id=p3.id,
                    input_data="5\n",
                    expected_output="120\n",
                    is_hidden=False,
                    points=20,
                    sort_order=2,
                ),
                TestCase(
                    problem_id=p3.id,
                    input_data="1\n",
                    expected_output="1\n",
                    is_hidden=True,
                    points=20,
                    sort_order=3,
                ),
                TestCase(
                    problem_id=p3.id,
                    input_data="10\n",
                    expected_output="3628800\n",
                    is_hidden=True,
                    points=20,
                    sort_order=4,
                ),
                TestCase(
                    problem_id=p3.id,
                    input_data="15\n",
                    expected_output="1307674368000\n",
                    is_hidden=True,
                    points=20,
                    sort_order=5,
                ),
            ]
            session.add_all(tcs_p3)
            print(f"Created Problem 3: 'Factorial of a Number' (ID: {p3.id}) with 5 test cases.")
        else:
            print(f"Problem 3 already exists (ID: {p3.id}).")

        await session.commit()
        print("Database problem seed completed successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
