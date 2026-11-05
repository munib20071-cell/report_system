import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'tvtc_institutional_pro_secret_key'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

reports = []


def clean_old_reports():
    global reports
    now = datetime.now()
    active_reports = []
    for r in reports:
        diff_days = (now - r['created_at']).days
        if r['status'] == 'مكتمل' and diff_days > 7:
            continue
        elif r['status'] != 'مكتمل' and diff_days > 30:
            continue
        active_reports.append(r)
    reports = active_reports


@app.route('/')
def index():
    clean_old_reports()
    return render_template('index.html')


@app.route('/user_form', methods=['GET', 'POST'])
def user_form():
    clean_old_reports()
    duplicate_error = None

    if request.method == 'POST':
        building = request.form.get('building', '').strip()
        floor = request.form.get('floor', '').strip()
        room = request.form.get('room', '').strip()
        full_location = f"المبنى: {building} | الدور: {floor} | القاعة: {room}"

        dev_num = request.form.get('device_number', '').strip()
        if not dev_num:
            dev_num = "-"

        device = request.form.get('device')
        if device == "أخرى":
            device = request.form.get('other_device', 'أخرى').strip()

        name = request.form.get('name', '').strip()
        training_id = request.form.get('training_id', '').strip()
        category = request.form.get('category', '').strip()

        problem = request.form.get('problem', '').strip()
        if problem == "أخرى (يرجى التحديد)":
            problem = request.form.get('other_problem', 'أخرى').strip()

        for r in reports:
            if (r['name'] == name and
                    r['training_id'] == training_id and
                    r['category'] == category and
                    r['device'] == device and
                    r['problem'] == problem and
                    r['location'] == full_location and
                    r['device_number'] == dev_num):
                duplicate_error = "تنبيه مؤسسي: يوجد بلاغ مطابق تماماً مسجل سابقاً في النظام!"
                return render_template('user_form.html', duplicate_error=duplicate_error)

        image_filenames = []
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
                        ext = '.png'
                    saved_name = f"report_{len(reports) + 1}_{len(image_filenames) + 1}{ext}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], saved_name))
                    image_filenames.append(saved_name)

        priority_score = 3
        if device == "كمبيوتر":
            priority_score = 1
        elif device == "الشاشة":
            priority_score = 2

        new_report = {
            'id': len(reports) + 1,
            'user_type': request.form.get('user_type'),
            'name': name,
            'training_id': training_id,
            'category': category,
            'device': device,
            'problem': problem,
            'location': full_location,
            'device_number': dev_num,
            'image_filenames': image_filenames,
            'status': 'قيد المعالجة',
            'created_at': datetime.now(),
            'priority_score': priority_score
        }
        reports.append(new_report)
        return redirect(url_for('track_report'))

    return render_template('user_form.html', duplicate_error=duplicate_error)


@app.route('/track', methods=['GET', 'POST'])
def track_report():
    clean_old_reports()
    search_results = []
    searched = False

    if request.method == 'POST':
        searched = True
        query = request.form.get('search_query', '').strip().lower()
        if query:
            for r in reports:
                if query in r['name'].lower() or query == r['training_id'].lower():
                    if r not in search_results:
                        search_results.append(r)

    return render_template('track_report.html', reports=search_results, searched=searched)


@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        if password == '2030':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = 'كلمة المرور غير صحيحة.'
    return render_template('index.html', error=error)


@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    global reports
    clean_old_reports()
    if not session.get('admin_logged_in'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update':
            try:
                rep_id = int(request.form.get('report_id'))
                new_status = request.form.get('new_status')
                for r in reports:
                    if r['id'] == rep_id:
                        r['status'] = new_status
                        break
            except (ValueError, TypeError):
                pass
        elif action == 'delete':
            try:
                rep_id = int(request.form.get('report_id'))
                reports = [r for r in reports if r['id'] != rep_id]
            except (ValueError, TypeError):
                pass

    filter_device = request.args.get('filter_device', 'all')
    filter_status = request.args.get('filter_status', 'all')

    display_reports = list(reports)
    if filter_device != 'all':
        display_reports = [r for r in display_reports if r['device'] == filter_device]
    if filter_status != 'all':
        display_reports = [r for r in display_reports if r['status'] == filter_status]

    display_reports.sort(key=lambda x: (x['priority_score'], -x['id']))

    stats = {
        'total': len(reports),
        'processing': sum(1 for r in reports if r['status'] == 'قيد المعالجة'),
        'working': sum(1 for r in reports if r['status'] == 'قيد العمل'),
        'completed': sum(1 for r in reports if r['status'] == 'مكتمل')
    }

    return render_template('admin_dashboard.html', reports=display_reports, stats=stats)


@app.route('/export_excel')
def export_excel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('index'))

    if not reports:
        return redirect(url_for('admin_dashboard'))

    data = []
    for r in reports:
        data.append({
            'رقم البلاغ': r['id'],
            'التاريخ والوقت': r['created_at'].strftime('%Y-%m-%d %H:%M'),
            'الصفة': r['user_type'],
            'الاسم': r['name'],
            'الرقم التدريبي': r['training_id'],
            'نوع المسار': r['category'],
            'نوع الجهاز': r['device'],
            'المشكلة': r['problem'],
            'الموقع': r['location'],
            'رقم الجهاز': r['device_number'],
            'عدد الصور المرفقة': len(r['image_filenames']),
            'حالة البلاغ': r['status']
        })

    df = pd.DataFrame(data)
    excel_path = 'tvtc_reports.xlsx'
    df.to_excel(excel_path, index=False)

    return send_file(excel_path, as_attachment=True, download_name='سجل_بلاغات_المؤسسة.xlsx')


@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)