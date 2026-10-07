from foodtrace.data.process import _match_commodity, traceability_checks

COMPLETE = {
    "code_info": "Lot 22451, Best By 03/14/2023",
    "product_quantity": "1,200 cases",
    "distribution_pattern": "Shipped to CA, AZ and NV.",
    "address_1": "100 Main St", "city": "Salinas", "postal_code": "93901",
}


def test_complete_record_passes_every_check():
    assert all(traceability_checks(COMPLETE).values())


def test_missing_lot_code_fails_only_that_check():
    rec = dict(COMPLETE, code_info="Best By 03/14/2023")
    checks = traceability_checks(rec)
    assert not checks["chk_lot"]
    assert checks["chk_date"] and checks["chk_quantity"]


def test_nationwide_is_not_a_specific_distribution():
    rec = dict(COMPLETE, distribution_pattern="Nationwide")
    assert not traceability_checks(rec)["chk_distribution"]


def test_quantity_needs_a_number_and_unit():
    assert not traceability_checks(dict(COMPLETE, product_quantity="unknown"))["chk_quantity"]
    assert traceability_checks(dict(COMPLETE, product_quantity="560 lbs"))["chk_quantity"]


def test_commodity_matching_uses_the_product_name():
    assert _match_commodity("Fresh Romaine Lettuce hearts, 3 count") == "lettuce"
    assert _match_commodity("Whole cantaloupe, PLU 4050") == "melon"


def test_processed_products_are_excluded():
    assert _match_commodity("Tomato soup, condensed, 10.75 oz can") is None
    assert _match_commodity("Onion powder, 16 oz") is None
