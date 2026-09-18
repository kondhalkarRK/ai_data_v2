from app.services.knowledge import extract_entities, infer_collection, suggested_questions_for


def test_infer_collection_from_filename() -> None:
    assert infer_collection("Q1 pack", "dealer_report.txt") == "dealer_reports"
    assert infer_collection("Catalog", "models.pdf") == "product_catalogs"


def test_extract_entities_finds_known_terms() -> None:
    found = extract_entities("Hyundai SUV demand in Mumbai rose.")
    assert "hyundai" in found
    assert "suv" in found
    assert "mumbai" in found


def test_suggested_questions_include_key_findings() -> None:
    questions = suggested_questions_for("sales_reports")
    assert "What are the key findings?" in questions
