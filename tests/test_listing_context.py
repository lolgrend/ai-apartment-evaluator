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
            title="Apartment in Jagodno",
            raw_text="Balcony, garage, and a good layout.",
            status="evaluated",
            price_pln=650_000,
            area_sqm=58,
            rooms=3,
            location="Jagodno",
            score=84,
            recommendation="yes",
            summary="Good price, weaker commute.",
            evaluation={"details": "The price is attractive, but the commute is long."},
        )
        self.private_other = Listing(
            user_id=self.other.id,
            title="Private apartment",
            raw_text="Should not be visible.",
        )
        self.shared_other = Listing(
            user_id=self.other.id,
            title="Shared apartment",
            raw_text="Visible to the household.",
            shared_with_household=True,
        )
        self.db.add_all([self.jagodno, self.private_other, self.shared_other])
        self.db.flush()
        self.db.add(ListingComment(
            listing_id=self.jagodno.id,
            user_id=self.user.id,
            body="Check evening noise.",
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
            "The price is attractive, but the commute is long.",
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
