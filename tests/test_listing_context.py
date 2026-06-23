from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.listing_context import accessible_listing_catalog, read_listing_details
from app.models import Listing, ListingComment, User


class ListingContextTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(username="owner", password_hash="hash", preferences={})
        self.other = User(username="other", password_hash="hash", preferences={})
        self.db.add_all([self.user, self.other])
        self.db.flush()

        self.jagodno = Listing(
            user_id=self.user.id,
            title="Mieszkanie na Jagodnie",
            raw_text="Balkon, garaż i dobry układ.",
            status="evaluated",
            price_pln=650_000,
            area_sqm=58,
            rooms=3,
            location="Jagodno",
            score=84,
            recommendation="yes",
            summary="Dobra cena, słabszy dojazd.",
            evaluation={"details": "Cena jest atrakcyjna, lecz dojazd trwa długo."},
        )
        self.private_other = Listing(
            user_id=self.other.id,
            title="Prywatne mieszkanie",
            raw_text="Nie powinno być widoczne.",
        )
        self.shared_other = Listing(
            user_id=self.other.id,
            title="Współdzielone mieszkanie",
            raw_text="Widoczne dla gospodarstwa domowego.",
            shared_with_household=True,
        )
        self.db.add_all([self.jagodno, self.private_other, self.shared_other])
        self.db.flush()
        self.db.add(ListingComment(
            listing_id=self.jagodno.id,
            user_id=self.user.id,
            body="Sprawdzić hałas wieczorem.",
            is_pinned=True,
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_reader_returns_full_details_and_never_exposes_private_record(self):
        result = read_listing_details(
            self.db, self.user, None, "Jagodno", 3
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["price_pln"], 650_000)
        self.assertEqual(result[0]["score"], 84)
        self.assertEqual(
            result[0]["evaluation"]["details"],
            "Cena jest atrakcyjna, lecz dojazd trwa długo.",
        )
        self.assertEqual(result[0]["user_comments"][0]["pinned"], True)

        hidden = read_listing_details(
            self.db, self.user, [self.private_other.id], None, 3
        )
        self.assertEqual(hidden, [])

    def test_catalog_includes_owned_and_household_shared_records(self):
        catalog = accessible_listing_catalog(self.db, self.user)
        ids = {item["id"] for item in catalog}

        self.assertIn(self.jagodno.id, ids)
        self.assertIn(self.shared_other.id, ids)
        self.assertNotIn(self.private_other.id, ids)


if __name__ == "__main__":
    unittest.main()
