# test_cyclic_import.py
import sys
from pathlib import Path

# Add project root to sys.path to allow importing 'examples.cyclic_server'
# This assumes the script is in 'project_root/examples/' and run from 'project_root'
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from examples.cyclic_server import Employee, Department, Company

    print("Successfully imported Employee, Department, Company models!")

    # Attempt to create instances
    print("Attempting to create model instances...")
    comp = Company(name="Tech Corp", departments=None)
    dept = Department(name="Engineering", members=None, company=comp)
    emp1 = Employee(name="Alice", id=1, department=dept, reports_to=None, manages=None) # Initially reports_to and manages are None
    emp2 = Employee(name="Bob", id=2, department=dept, reports_to=emp1, manages=None)

    # Establish cyclic links
    emp1.manages = [emp2]
    dept.members = [emp1, emp2]
    comp.departments = [dept]

    print("Successfully created model instances with cyclic dependencies.")
    print(f"Employee: {emp1.name}, Manages: {[e.name for e in emp1.manages]}, Reports to: {emp1.reports_to.name if emp1.reports_to else 'N/A'}, Department: {emp1.department.name}")
    print(f"Employee: {emp2.name}, Manages: {[e.name for e in emp2.manages] if emp2.manages else 'N/A'}, Reports to: {emp2.reports_to.name if emp2.reports_to else 'N/A'}, Department: {emp2.department.name}")
    print(f"Department: {dept.name}, Members: {[m.name for m in dept.members]}, Company: {dept.company.name}")
    print(f"Company: {comp.name}, Departments: {[d.name for d in comp.departments]}")

except ImportError as e:
    print(f"ImportError: {e}")
    print("Failed to import models. Check PYTHONPATH or if the generated server has issues.")
    print("Ensure you are running this script from the project root directory (e.g., python examples/test_cyclic_import.py)")
except Exception as e:
    print(f"An error occurred during model instantiation or use: {e}")
    import traceback
    traceback.print_exc()
