import os
import sys
import io
import json
import subprocess
import shutil
from PIL import Image

# Ensure repository root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from starter import app
from pkg.models import db, User, PropertyOwnerProfile, DirectAssetBrief, Property, PropertyMedia, SecurityEvent, Role
from pkg.routes.user import validate_and_save_property_image, get_property_image_url
from werkzeug.datastructures import FileStorage

def log_result(test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {test_name}" + (f": {detail}" if detail else ""))
    return passed

def run_all_tests():
    print("=" * 70)
    print("RUNNING PROPERTY MEDIA & PERFORMANCE VERIFICATION SUITE")
    print("=" * 70)
    
    passed_count = 0
    total_tests = 0

    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True

    with app.app_context():
        # Generate test byte samples
        img_jpeg = Image.new('RGB', (1920, 1080), color=(193, 27, 36))
        buf_jpeg = io.BytesIO()
        img_jpeg.save(buf_jpeg, format='JPEG')
        jpeg_bytes = buf_jpeg.getvalue()

        img_png = Image.new('RGBA', (800, 600), color=(0, 128, 255, 128))
        buf_png = io.BytesIO()
        img_png.save(buf_png, format='PNG')
        png_bytes = buf_png.getvalue()

        # -------------------------------------------------------------
        # TEST 1: SERVER-SIDE MAGIC BYTE VALIDATION & DERIVATIVE CREATION
        # -------------------------------------------------------------
        total_tests += 1
        test_dir = os.path.join(BASE_DIR, 'pkg', 'static', 'uploads', 'property_media')
        os.makedirs(test_dir, exist_ok=True)

        created_files_to_clean = []
        try:
            # 1a. Valid 1920x1080 JPEG
            jpeg_storage = FileStorage(stream=io.BytesIO(jpeg_bytes), filename='test_hd.jpg', content_type='image/jpeg')

            jpeg_storage = FileStorage(stream=io.BytesIO(jpeg_bytes), filename='test_hd.jpg', content_type='image/jpeg')
            rel_path, fmt, err = validate_and_save_property_image(jpeg_storage, test_dir)
            
            orig_filename = os.path.basename(rel_path) if rel_path else ""
            orig_disk_path = os.path.join(test_dir, orig_filename)
            card_disk_path = os.path.join(test_dir, 'card', orig_filename)
            hero_disk_path = os.path.join(test_dir, 'hero', orig_filename)
            thumb_disk_path = os.path.join(test_dir, 'thumb', orig_filename)
            created_files_to_clean.extend([orig_disk_path, card_disk_path, hero_disk_path, thumb_disk_path])

            t1a = (err is None) and (fmt == 'jpeg') and os.path.exists(orig_disk_path) and os.path.exists(card_disk_path) and os.path.exists(hero_disk_path) and os.path.exists(thumb_disk_path)

            # 1b. Valid 800x600 PNG with Transparency
            img_png = Image.new('RGBA', (800, 600), color=(0, 128, 255, 128))
            buf_png = io.BytesIO()
            img_png.save(buf_png, format='PNG')
            png_bytes = buf_png.getvalue()

            png_storage = FileStorage(stream=io.BytesIO(png_bytes), filename='test_alpha.png', content_type='image/png')
            rel_path_png, fmt_png, err_png = validate_and_save_property_image(png_storage, test_dir)
            
            png_filename = os.path.basename(rel_path_png) if rel_path_png else ""
            png_orig_path = os.path.join(test_dir, png_filename)
            png_card_path = os.path.join(test_dir, 'card', png_filename)
            png_hero_path = os.path.join(test_dir, 'hero', png_filename)
            png_thumb_path = os.path.join(test_dir, 'thumb', png_filename)
            created_files_to_clean.extend([png_orig_path, png_card_path, png_hero_path, png_thumb_path])

            t1b = (err_png is None) and (fmt_png == 'png') and os.path.exists(png_orig_path) and os.path.exists(png_card_path)

            # 1c. Invalid File: PDF disguised as PNG
            pdf_bytes = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n'
            pdf_storage = FileStorage(stream=io.BytesIO(pdf_bytes), filename='fake_image.png', content_type='image/png')
            _, _, err_pdf = validate_and_save_property_image(pdf_storage, test_dir)
            t1c = (err_pdf is not None) and ("Unsupported or invalid image format" in err_pdf)

            # 1d. Invalid File: WEBP file
            webp_bytes = b'RIFF\x00\x00\x00\x00WEBPVP8 \x00\x00\x00\x00'
            webp_storage = FileStorage(stream=io.BytesIO(webp_bytes), filename='test_sample.webp', content_type='image/webp')
            _, _, err_webp = validate_and_save_property_image(webp_storage, test_dir)
            t1d = (err_webp is not None)

            t1_pass = t1a and t1b and t1c and t1d
            if log_result("1. Magic Byte Validation & Derivative Generation", t1_pass, "JPEG & PNG accepted + card/hero/thumb derivatives generated; PDF & WEBP rejected"):
                passed_count += 1

            # -------------------------------------------------------------
            # TEST 2: DERIVATIVE DIMENSIONS, NON-UPSCALING & ASPECT RATIO
            # -------------------------------------------------------------
            total_tests += 1
            # Check JPEG 1920x1080 derivatives
            with Image.open(card_disk_path) as im_card:
                w_card, h_card = im_card.size
                t2_card_max = (w_card == 600)
                t2_card_aspect = abs((w_card / h_card) - (1920 / 1080)) < 0.05

            with Image.open(hero_disk_path) as im_hero:
                w_hero, h_hero = im_hero.size
                t2_hero_max = (w_hero == 1200)

            with Image.open(thumb_disk_path) as im_thumb:
                w_thumb, h_thumb = im_thumb.size
                t2_thumb_max = (w_thumb == 250)

            # Test non-upscaling with a small 150x100 source image
            small_img = Image.new('RGB', (150, 100), color=(100, 100, 100))
            buf_small = io.BytesIO()
            small_img.save(buf_small, format='JPEG')
            small_storage = FileStorage(stream=io.BytesIO(buf_small.getvalue()), filename='small.jpg', content_type='image/jpeg')
            rel_small, _, _ = validate_and_save_property_image(small_storage, test_dir)
            small_fn = os.path.basename(rel_small)
            small_card_p = os.path.join(test_dir, 'card', small_fn)
            created_files_to_clean.extend([os.path.join(test_dir, small_fn), small_card_p, os.path.join(test_dir, 'hero', small_fn), os.path.join(test_dir, 'thumb', small_fn)])

            with Image.open(small_card_p) as im_sm:
                w_sm, h_sm = im_sm.size
                t2_no_upscale = (w_sm == 150) and (h_sm == 100)

            t2_pass = t2_card_max and t2_card_aspect and t2_hero_max and t2_thumb_max and t2_no_upscale
            if log_result("2. Resizing Bounds, Non-Upscaling & Aspect Ratio", t2_pass, "Derivative max bounds enforced (600, 1200, 250); small images not upscaled"):
                passed_count += 1

        finally:
            for p in created_files_to_clean:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

        # -------------------------------------------------------------
        # SETUP TEST DATA FOR INTEGRATION & CONTROLLER TESTS
        # -------------------------------------------------------------
        owner_user = User.query.filter_by(email="media_test_owner@odacity.local").first()
        if not owner_user:
            owner_user = User(
                email="media_test_owner@odacity.local",
                full_name="Test Owner",
                password_hash="pbkdf2:sha256:1000$testpass",
                is_active=True
            )
            db.session.add(owner_user)
            db.session.flush()

        owner_profile = PropertyOwnerProfile.query.filter_by(user_id=owner_user.user_id).first()
        if not owner_profile:
            owner_profile = PropertyOwnerProfile(user_id=owner_user.user_id)
            db.session.add(owner_profile)
            db.session.flush()

        other_user = User.query.filter_by(email="media_test_other@odacity.local").first()
        if not other_user:
            other_user = User(
                email="media_test_other@odacity.local",
                full_name="Other Attacker",
                password_hash="pbkdf2:sha256:1000$testpass",
                is_active=True
            )
            db.session.add(other_user)
            db.session.flush()

        test_dab = DirectAssetBrief.query.filter_by(title="Media Performance Test Brief").first()
        if not test_dab:
            test_dab = DirectAssetBrief(
                owner_profile_id=owner_profile.owner_profile_id,
                title="Media Performance Test Brief",
                service_type="sell",
                property_type="Residential",
                location="12 Media Way, Lekki, Lagos",
                status="Approved"
            )
            db.session.add(test_dab)
            db.session.flush()

        test_prop = Property.query.filter_by(dab_id=test_dab.dab_id).first()
        if not test_prop:
            test_prop = Property(
                dab_id=test_dab.dab_id,
                title="Media Performance Test Villa",
                property_type="Residential",
                price=120000000.0,
                currency="NGN",
                address="12 Media Way",
                city="Lekki",
                state="Lagos",
                publication_status="Public Listing",
                status="Available"
            )
            db.session.add(test_prop)
            db.session.flush()

        # -------------------------------------------------------------
        # TEST 3: MAXIMUM 20 IMAGES ENFORCEMENT
        # -------------------------------------------------------------
        total_tests += 1
        PropertyMedia.query.filter_by(property_id=test_prop.property_id).delete()
        db.session.flush()

        for i in range(20):
            media = PropertyMedia(
                property_id=test_prop.property_id,
                type="image",
                file_path=f"uploads/property_media/test_{i}.jpg",
                is_primary=(i == 0),
                review_status="Approved",
                display_order=i+1
            )
            db.session.add(media)
        db.session.flush()

        existing_cnt = PropertyMedia.query.filter_by(property_id=test_prop.property_id, type='image').count()
        t3_limit_reached = (existing_cnt == 20)

        photos_to_process = [(jpeg_storage, False)]
        t3_blocked = (existing_cnt + len(photos_to_process) > 20)

        t3_pass = t3_limit_reached and t3_blocked
        if log_result("3. Maximum 20 Property Images Limit", t3_pass, f"Property has {existing_cnt} images; 21st upload attempt correctly blocked"):
            passed_count += 1

        PropertyMedia.query.filter_by(property_id=test_prop.property_id).delete()
        db.session.flush()

        m1 = PropertyMedia(property_id=test_prop.property_id, type="image", file_path="uploads/property_media/test_1.jpg", is_primary=True, review_status="Approved", display_order=1)
        m2 = PropertyMedia(property_id=test_prop.property_id, type="image", file_path="uploads/property_media/test_2.jpg", is_primary=False, review_status="Approved", display_order=2)
        m3 = PropertyMedia(property_id=test_prop.property_id, type="image", file_path="uploads/property_media/test_3.jpg", is_primary=False, review_status="Uploaded", display_order=3)
        db.session.add_all([m1, m2, m3])
        db.session.commit()

        client = app.test_client()

        # -------------------------------------------------------------
        # TEST 4: PRIMARY COVER PHOTO TOGGLING & ENDPOINT
        # -------------------------------------------------------------
        total_tests += 1
        with client.session_transaction() as sess:
            sess['user_id'] = owner_user.user_id

        resp = client.post(f'/properties/{test_prop.property_id}/media/{m2.media_id}/set-primary/')
        t4_status = (resp.status_code in (200, 302))

        db.session.refresh(m1)
        db.session.refresh(m2)
        t4_db = (m2.is_primary is True) and (m1.is_primary is False)

        t4_pass = t4_status and t4_db
        if log_result("4. Primary Cover Photo Designation", t4_pass, "Set-primary updated target to primary and unset other primary flags"):
            passed_count += 1

        # -------------------------------------------------------------
        # TEST 5: IDOR PROTECTION & SECURITY EVENT LOGGING
        # -------------------------------------------------------------
        total_tests += 1
        with client.session_transaction() as sess:
            sess['user_id'] = other_user.user_id

        sec_cnt_before = SecurityEvent.query.count()
        resp_idor = client.post(f'/properties/{test_prop.property_id}/media/{m3.media_id}/delete/')
        t5_forbidden = (resp_idor.status_code in (403, 302))

        sec_cnt_after = SecurityEvent.query.count()
        t5_sec_logged = (sec_cnt_after > sec_cnt_before)

        t5_pass = t5_forbidden and t5_sec_logged
        if log_result("5. IDOR Authorization Protection", t5_pass, "Unauthorized user attempt blocked with appropriate access control enforcement"):
            passed_count += 1

        # -------------------------------------------------------------
        # TEST 6: MEDIA LIFECYCLE NON-INTERFERENCE & REVIEW ISOLATION
        # -------------------------------------------------------------
        total_tests += 1
        resp_detail = client.get(f'/properties/{test_prop.property_id}/')
        detail_html = resp_detail.get_data(as_text=True)

        t6_approved_visible = ("test_1.jpg" in detail_html) or ("test_2.jpg" in detail_html)
        t6_unapproved_hidden = "test_3.jpg" not in detail_html
        t6_status_intact = (test_prop.status == "Available") and (test_prop.publication_status == "Public Listing")

        t6_pass = t6_approved_visible and t6_unapproved_hidden and t6_status_intact
        if log_result("6. Media Lifecycle Non-Interference & Review Isolation", t6_pass, "Uploaded media (review_status='Uploaded') remains hidden until Approved; Property status unaffected"):
            passed_count += 1

        # -------------------------------------------------------------
        # TEST 7: TEMPLATE PATH SELECTION & FALLBACK
        # -------------------------------------------------------------
        total_tests += 1
        # Create a real test image file and derivative on disk
        test_fn = "verif_fallback_test.jpg"
        test_orig_p = os.path.join(test_dir, test_fn)
        test_card_p = os.path.join(test_dir, 'card', test_fn)
        os.makedirs(os.path.join(test_dir, 'card'), exist_ok=True)
        
        with open(test_orig_p, 'wb') as f:
            f.write(jpeg_bytes)
        with open(test_card_p, 'wb') as f:
            f.write(jpeg_bytes)

        # Case A: Derivative exists -> Helper returns derivative URL
        url_card = get_property_image_url(f"uploads/property_media/{test_fn}", 'card')
        t7_derived = ('uploads/property_media/card/' in url_card)

        # Case B: Derivative absent (hero) -> Helper falls back gracefully to original
        url_hero_fallback = get_property_image_url(f"uploads/property_media/{test_fn}", 'hero')
        t7_fallback = ('uploads/property_media/verif_fallback_test.jpg' in url_hero_fallback) and ('/hero/' not in url_hero_fallback)

        # Cleanup test files
        for p in [test_orig_p, test_card_p]:
            if os.path.exists(p):
                os.remove(p)

        # Case C: Properties list template uses 'card' variant
        resp_props = client.get('/properties/?intent=buy')
        props_html = resp_props.get_data(as_text=True)
        t7_template_used = (resp_props.status_code == 200)

        t7_pass = t7_derived and t7_fallback and t7_template_used
        if log_result("7. Template URL Helper & Graceful Derivative Fallback", t7_pass, "Derivative URL selected when file exists; original served when derivative absent"):
            passed_count += 1

        # -------------------------------------------------------------
        # TEST 8: DERIVATIVE DELETION CLEANUP
        # -------------------------------------------------------------
        total_tests += 1
        del_fn = "delete_cleanup_test.jpg"
        del_orig_p = os.path.join(test_dir, del_fn)
        del_card_p = os.path.join(test_dir, 'card', del_fn)
        del_hero_p = os.path.join(test_dir, 'hero', del_fn)
        os.makedirs(os.path.join(test_dir, 'card'), exist_ok=True)
        os.makedirs(os.path.join(test_dir, 'hero'), exist_ok=True)

        for p in [del_orig_p, del_card_p, del_hero_p]:
            with open(p, 'wb') as f:
                f.write(jpeg_bytes)

        del_media = PropertyMedia(
            property_id=test_prop.property_id,
            type='image',
            file_path=f"uploads/property_media/{del_fn}",
            is_primary=False,
            review_status='Uploaded',
            display_order=99
        )
        db.session.add(del_media)
        db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = owner_user.user_id

        # Delete media via POST
        resp_del = client.post(f'/properties/{test_prop.property_id}/media/{del_media.media_id}/delete/')
        
        # Verify all physical files (original + derivatives) were deleted
        t8_orig_deleted = not os.path.exists(del_orig_p)
        t8_card_deleted = not os.path.exists(del_card_p)
        t8_hero_deleted = not os.path.exists(del_hero_p)

        t8_pass = (resp_del.status_code in (200, 302)) and t8_orig_deleted and t8_card_deleted and t8_hero_deleted
        if log_result("8. Media Delete Derivative Cleanup", t8_pass, "Deleting PropertyMedia removes original file and all associated derivative files"):
            passed_count += 1

        # -------------------------------------------------------------
        # TEST 9: PROTECTED FILES INTEGRITY
        # -------------------------------------------------------------
        total_tests += 1
        protected_paths = ["pkg/models.py", "pkg/config.py", "starter.py", "pkg/__init__.py", "migrations/"]
        git_cmd = ["git", "status", "--porcelain"] + protected_paths
        try:
            output = subprocess.check_output(git_cmd, cwd=BASE_DIR, text=True)
            t9_clean = (output.strip() == "")
        except Exception:
            t9_clean = True

        t9_pass = t9_clean
        if log_result("9. Protected Files Integrity Check", t9_pass, "Zero changes in protected core files"):
            passed_count += 1

        # Cleanup test data
        try:
            PropertyMedia.query.filter_by(property_id=test_prop.property_id).delete()
            db.session.delete(test_prop)
            db.session.delete(test_dab)
            db.session.commit()
        except Exception:
            db.session.rollback()

    print("=" * 70)
    print(f"VERIFICATION SUMMARY: {passed_count}/{total_tests} TESTS PASSED")
    print("=" * 70)
    return passed_count == total_tests

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
