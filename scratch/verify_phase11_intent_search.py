import os
import sys
import unittest
from datetime import datetime, timedelta

# Ensure project root is in sys.path
PROJECT_ROOT = r'c:\Users\User\Desktop\Odacity-MVP2025'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pkg import app
from pkg.models import (
    db, User, PropertyOwnerProfile, DirectAssetBrief, Property
)

class Phase11IntentSearchTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # Seed Owner User & Profile
        self.owner_user = User.query.filter_by(email='owner_p11@odacity.com').first()
        if not self.owner_user:
            self.owner_user = User(
                email='owner_p11@odacity.com',
                password_hash='pbkdf2:sha256:test',
                full_name='Owner P11',
                is_active=True,
                is_super_admin=False,
                created_at=datetime.utcnow()
            )
            db.session.add(self.owner_user)
            db.session.flush()

        self.owner_prof = PropertyOwnerProfile.query.filter_by(user_id=self.owner_user.user_id).first()
        if not self.owner_prof:
            self.owner_prof = PropertyOwnerProfile(
                user_id=self.owner_user.user_id,
                company_name='Owner P11 Corp',
                owner_type='individual',
                is_approved=True,
                created_at=datetime.utcnow()
            )
            db.session.add(self.owner_prof)
            db.session.commit()

        # Clean existing test properties for clear assertions
        test_dabs = DirectAssetBrief.query.filter_by(owner_profile_id=self.owner_prof.owner_profile_id).all()
        for dab in test_dabs:
            Property.query.filter_by(dab_id=dab.dab_id).delete()
            db.session.delete(dab)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def create_property(self, title, service_type, publication_status='Public Listing', 
                        state='Lagos', city='Ikeja', locality=None, location=None, 
                        address=None, price=100000.0, approved_hours_ago=100):
        if locality is None:
            locality = f"{city} Center"
        if location is None:
            location = f"{city} Area"
        if address is None:
            address = f"123 {city} St"
        dab = DirectAssetBrief(
            owner_profile_id=self.owner_prof.owner_profile_id,
            title=f"DAB {title}",
            service_type=service_type,
            status='Approved',
            approved_at=datetime.utcnow() - timedelta(hours=approved_hours_ago),
            created_at=datetime.utcnow() - timedelta(hours=approved_hours_ago)
        )
        db.session.add(dab)
        db.session.flush()

        prop = Property(
            dab_id=dab.dab_id,
            title=title,
            property_type='Residential',
            state=state,
            city=city,
            locality=locality,
            location=location,
            address=address,
            price=price,
            status='Approved',
            publication_status=publication_status,
            created_at=datetime.utcnow() - timedelta(hours=approved_hours_ago)
        )
        db.session.add(prop)
        db.session.commit()
        return prop

    def test_01_buyer_returns_only_sale(self):
        """Test 1: Buyer (intent=buy) returns ONLY sale properties."""
        p_sale = self.create_property(title="Buy Prop 1", service_type="sale")
        p_rent = self.create_property(title="Rent Prop 1", service_type="rent")

        res = self.client.get('/properties/?intent=buy')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Buy Prop 1", html)
        self.assertNotIn("Rent Prop 1", html)

    def test_02_renter_returns_only_rent_lease(self):
        """Test 2: Renter (intent=rent) returns ONLY rent/lease properties."""
        p_sale = self.create_property(title="Buy Prop 2", service_type="sale")
        p_rent = self.create_property(title="Rent Prop 2", service_type="rent")
        p_lease = self.create_property(title="Lease Prop 2", service_type="lease")

        res = self.client.get('/properties/?intent=rent')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("Buy Prop 2", html)
        self.assertIn("Rent Prop 2", html)
        self.assertIn("Lease Prop 2", html)

    def test_03_same_location_rent_vs_sale_separation(self):
        """Test 3: Same location Rent vs Sale separation."""
        p_sale = self.create_property(title="Ikeja Mansion Sale", service_type="sale", city="Ikeja")
        p_rent = self.create_property(title="Ikeja Apartment Rent", service_type="rent", city="Ikeja")

        # Renter search in Ikeja
        res_rent = self.client.get('/properties/?intent=rent&location=Ikeja')
        html_rent = res_rent.data.decode('utf-8')
        self.assertIn("Ikeja Apartment Rent", html_rent)
        self.assertNotIn("Ikeja Mansion Sale", html_rent)

        # Buyer search in Ikeja
        res_buy = self.client.get('/properties/?intent=buy&location=Ikeja')
        html_buy = res_buy.data.decode('utf-8')
        self.assertIn("Ikeja Mansion Sale", html_buy)
        self.assertNotIn("Ikeja Apartment Rent", html_buy)

    def test_04_city_search(self):
        """Test 4: City Search (location=Ikeja)."""
        p_ikeja = self.create_property(title="Prop Ikeja", service_type="sale", city="Ikeja", state="Lagos")
        p_abuja = self.create_property(title="Prop Abuja", service_type="sale", city="Abuja", state="FCT")

        res = self.client.get('/properties/?intent=buy&location=Ikeja')
        html = res.data.decode('utf-8')
        self.assertIn("Prop Ikeja", html)
        self.assertNotIn("Prop Abuja", html)

    def test_05_locality_search(self):
        """Test 5: Locality Search (location=Lekki Phase 1)."""
        p_lekki = self.create_property(title="Prop Lekki", service_type="sale", locality="Lekki Phase 1")
        p_yaba = self.create_property(title="Prop Yaba", service_type="sale", locality="Yaba")

        res = self.client.get('/properties/?intent=buy&location=Lekki Phase 1')
        html = res.data.decode('utf-8')
        self.assertIn("Prop Lekki", html)
        self.assertNotIn("Prop Yaba", html)

    def test_06_different_location_exclusion(self):
        """Test 6: Different location exclusion (location=Abuja)."""
        p_lagos = self.create_property(title="Lagos Villa", service_type="sale", state="Lagos", city="Ikeja")
        res = self.client.get('/properties/?intent=buy&location=Abuja')
        html = res.data.decode('utf-8')
        self.assertNotIn("Lagos Villa", html)

    def test_07_sold_excluded(self):
        """Test 7: Sold excluded."""
        p_sold = self.create_property(title="Sold House", service_type="sale", publication_status="Sold")
        res = self.client.get('/properties/?intent=buy')
        html = res.data.decode('utf-8')
        self.assertNotIn("Sold House", html)

    def test_08_unavailable_excluded(self):
        """Test 8: Unavailable excluded."""
        p_unavail = self.create_property(title="Unavail Flat", service_type="rent", publication_status="Unavailable")
        res = self.client.get('/properties/?intent=rent')
        html = res.data.decode('utf-8')
        self.assertNotIn("Unavail Flat", html)

    def test_09_private_listing_under_72h_excluded(self):
        """Test 9: Private Listing <72h excluded."""
        p_recent_priv = self.create_property(
            title="Recent Private", service_type="sale", 
            publication_status="Private Listing", approved_hours_ago=10
        )
        res = self.client.get('/properties/?intent=buy')
        html = res.data.decode('utf-8')
        self.assertNotIn("Recent Private", html)

    def test_10_public_listing_included(self):
        """Test 10: Public Listing included when matching."""
        p_pub = self.create_property(title="Public Listing Property", service_type="sale", publication_status="Public Listing")
        res = self.client.get('/properties/?intent=buy')
        html = res.data.decode('utf-8')
        self.assertIn("Public Listing Property", html)

    def test_11_missing_intent_redirects(self):
        """Test 11: Missing intent redirects/handles safely."""
        res = self.client.get('/properties/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/properties/?intent=buy', res.location)

    def test_12_invalid_intent_redirects(self):
        """Test 12: Invalid intent handles safely."""
        res = self.client.get('/properties/?intent=invalid_xyz')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/properties/?intent=buy', res.location)

if __name__ == '__main__':
    unittest.main()
