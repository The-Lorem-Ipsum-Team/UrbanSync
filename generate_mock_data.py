# FILE: generate_mock_data.py
"""Generate realistic mock data for UrbanSync Khon Kaen pipeline testing."""

import random
from pathlib import Path
import pandas as pd
import numpy as np

def generate_traffic_data(output_path: Path):
    """Generate mock traffic_dashboard.csv with 25 checkpoints."""
    roads = [
        "ถ.มิตรภาพ", "ถ.ศรีจันทร์", "ถ.กสิกรทุ่งสร้าง", "ถ.รื่นรมย์", "ถ.กลางเมือง",
        "ถ.หน้าเมือง", "ถ.ดรุณสำราญ", "ถ.ประชาสโมสร", "ถ.เหล่านาดี", "ถ.ชาตะผดุง",
        "ถ.ชีท่าขอน", "ถ.ชวนชื่น", "ถ.เทพารักษ์", "ถ.หลังเมือง", "ถ.พิมพสุต"
    ]
    locations = [
        "หน้า รร. ดอนบอสโก", "สี่แยกสามเหลี่ยม", "หน้า ม.ขอนแก่น", "สี่แยกกัลปพฤกษ์",
        "หน้าศูนย์ราชการ", "หน้าสวนรัชดานุสรณ์", "หน้าห้างเซ็นทรัลพลาซ่า", "หน้า บขส. 3",
        "หน้าตลาดบางลำภู", "หน้าตลาดโต้รุ่ง", "หน้าศาลหลักเมือง", "สี่แยกเจริญศรี",
        "หน้าวัดหนองแวง", "ริมบึงแก่นนคร", "หน้าโรงพยาบาลขอนแก่นราม"
    ]

    data = []
    for i in range(1, 26):
        road = random.choice(roads)
        loc = random.choice(locations) + f" (จุดที่ {i})"
        
        # Latitude: 16.37 to 16.49, Longitude: 102.78 to 102.85
        lat = round(random.uniform(16.37, 16.49), 6)
        lng = round(random.uniform(102.78, 102.85), 6)
        
        # Vehicle ranges matching prompt.txt
        car = random.randint(18913, 66220)
        motorcycle = random.randint(1667, 47205)
        truck = random.randint(2681, 19043)
        bus = random.randint(500, 4500)
        total = car + motorcycle + truck + bus
        vph = int(total / random.uniform(18, 24))
        
        data.append({
            "ที่": i,
            "เส้นทาง": road,
            "ตำแหน่งติดตั้งเครื่องวัด": loc,
            "Lat": lat,
            "Lag": lng, # Use 'Lag' to test normalization to 'Lng'
            "Car": car,
            "Motorcycle": motorcycle,
            "Truck": truck,
            "Bus": bus,
            "รวมต่อวัน": total,
            "คัน/ชั่วโมง": vph
        })
        
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Generated mock traffic data -> {output_path}")


def generate_complaints_data(output_path: Path):
    """Generate mock complaints.xlsx with ~46189 rows."""
    departments = ["ส่วนงานสาธารณสุข", "ส่วนงานช่าง", "ส่วนงานจราจร", "ส่วนงานเทศกิจ", "ส่วนงานปกครอง"]
    divisions = ["ฝ่ายรักษาความสงบ", "ฝ่ายวิศวกรรมการจราจร", "ฝ่ายควบคุมอาคาร", "ฝ่ายสุขาภิบาล", "ฝ่ายบำรุงทาง"]
    
    complaint_types = [
        "น้ำท่วม", "ถนน", "วิศวกรรมจราจร", "ท่อระบายน้ำ", "ไฟจราจร",
        "ไฟฟ้าขยายเขต", "ไฟฟ้า", "งานตัดกิ่งไม้และเกาะกลางถนน", "งานอื่น ๆ",
        "งานบำบัดน้ำเสีย", "งานกำจัดขยะมูลฝอยและสิ่งปฏิกูล", "งานอาคาร"
    ]
    
    thai_subjects = {
        "น้ำท่วม": [
            "น้ำท่วมขังรอการระบายหน้าหมู่บ้าน", "น้ำท่วมถนนสัญจรลำบากมาก ด่วน",
            "ท่อระบายน้ำอุดตันทำให้น้ำท่วมเวลาฝนตก", "น้ำท่วมสูงลึกถึงเข่า รถเล็กผ่านไม่ได้"
        ],
        "ถนน": [
            "ถนนเป็นหลุมบ่อขนาดใหญ่ รถจักรยานยนต์ล้มบ่อย อันตรายมาก",
            "ถนนทรุดตัว คอนกรีตแตก ชำรุดเสียหายหนัก", "พบเศษหินและทรายขวางการจราจรบนถนน",
            "ผิวทางพังชำรุดเป็นหลุมลึกยาวกว่า 10 เมตร"
        ],
        "วิศวกรรมจราจร": [
            "ป้ายสัญญาณจราจรชำรุดหักล้มขวางทางเดินเท้า", "เส้นจราจรลบเลือนมองไม่เห็นเวลากลางคืน",
            "ต้องการแผงกั้นทางจราจรเพื่อป้องกันอุบัติเหตุ", "ไหล่ทางแคบและชำรุดกรุณาแก้ไขด่วน"
        ],
        "ท่อระบายน้ำ": [
            "ฝาท่อระบายน้ำแตกชำรุด เกรงว่าจะมีคนตกตึกได้รับอันตราย",
            "กลิ่นเหม็นจากท่อระบายน้ำอุดตันสกปรกมาก", "ฝาท่อระบายน้ำทรุดตัวต่ำกว่าผิวถนน รถกระแทกแรง",
            "มีขยะเศษดินอุดตันทางระบายน้ำไหลช้ามาก"
        ],
        "ไฟจราจร": [
            "ไฟสัญญาณจราจรแยกไฟแดงดับหมดทุกสี เกิดอุบัติเหตุบ่อย",
            "ไฟสัญญาณจราจรขัดข้อง ติดไฟแดงค้างนานเกินไป", "ไฟกะพริบเตือนดับชำรุดกังวลเรื่องอันตราย",
            "เสาไฟสัญญาณจราจรเอียงเสี่ยงล้มทับรถ"
        ],
        "ไฟฟ้า": [
            "ไฟกิ่งไฟฟ้าสาธารณะดับมืดตลอดทั้งซอย อันตรายต่อการสัญจร",
            "สายไฟขาดห้อยย้อยลงมาต่ำมาก กลัวไฟช็อตและระเบิด",
            "เสาไฟฟ้าเอียงชำรุดเสียหายจากอุบัติเหตุรถชน", "กล่องควบคุมไฟฟ้าชำรุดมีเสียงดังและมีประกายไฟ"
        ],
        "งานตัดกิ่งไม้และเกาะกลางถนน": [
            "กิ่งไม้ใหญ่พาดสายไฟแรงสูง ลมพัดแรงมีประกายไฟน่ากลัว",
            "ต้นไม้ริมทางล้มขวางถนน รถสัญจรไม่ได้เลย ด่วนที่สุด",
            "หญ้าเกาะกลางถนนขึ้นสูงบดบังทัศนวิสัยผู้ขับขี่", "กิ่งไม้แห้งร่วงหล่นใส่หลังคารถยนต์ชำรุด"
        ],
        "งานอื่น ๆ": [
            "พบสุนัขจรจัดดุร้ายไล่กัดคนเดินเท้าในชุมชน", "เสียงดังรบกวนจากร้านค้าข้างบ้านในยามวิกาล",
            "มีผู้นำขยะมาทิ้งบริเวณพื้นที่รกร้างส่งกลิ่นเหม็นสกปรก"
        ]
    }
    
    districts = ["เขต 1", "เขต 2", "เขต 3", "เขต 4", "ไม่ระบุ"]
    communities = ["ชุมชนสามเหลี่ยม", "ชุมชนหนองแวงเทศบาล", "ชุมชนวัดหนองแวง", "ชุมชนโนนทัน", "ชุมชนเคหะ", "ไม่ระบุ"]
    statuses = ["รอช่างรับเรื่อง", "กำลังดำเนินการ", "อยู่ระหว่างการติดตาม", "เกินกำหนด", "ส่งต่อหน่วยงานอื่น", "ประเมินผลเสร็จสิ้น"]
    
    data = []
    # Generate 46189 records
    for i in range(1, 46190):
        dept = random.choice(departments)
        div = random.choice(divisions)
        ref_num = f"REQ-{2026:04d}{i:04d}"
        
        comp_type = random.choice(complaint_types)
        
        # Get appropriate subject
        subj_lookup = comp_type
        if comp_type not in thai_subjects:
            if "ไฟฟ้า" in comp_type:
                subj_lookup = "ไฟฟ้า"
            else:
                subj_lookup = "งานอื่น ๆ"
        subject = random.choice(thai_subjects[subj_lookup])
        
        # Randomly inject emergency words
        if random.random() < 0.25:
            subject += " " + random.choice(["ด่วนที่สุด", "ฉุกเฉิน", "อันตรายมาก", "เสียหายพังยับ"])
            
        district = random.choice(districts)
        community = random.choice(communities)
        
        # Date received: Buddhist Era year 2568-2569 (CE 2025-2026)
        # format DD/MM/YYYY
        day = random.randint(1, 28)
        month = random.randint(1, 12)
        buddhist_year = random.choice([2568, 2569])
        
        date_received_str = f"{day:02d}/{month:02d}/{buddhist_year}"
        
        # Status
        status = random.choice(statuses)
        
        # Date completed: only if closed (ประเมินผลเสร็จสิ้น)
        if status == "ประเมินผลเสร็จสิ้น":
            # Completed a few days after received
            comp_day = day + random.randint(1, 15)
            comp_month = month
            comp_year = buddhist_year
            if comp_day > 28:
                comp_day = comp_day - 28
                comp_month += 1
                if comp_month > 12:
                    comp_month = 1
                    comp_year += 1
            date_completed_str = f"{comp_day:02d}/{comp_month:02d}/{comp_year}"
        else:
            date_completed_str = ""
            
        data.append({
            "ส่วนงาน": dept,
            "ฝ่าย": div,
            "เลขคำร้อง": ref_num,
            "เรื่องร้องทุกข์": subject,
            "ประเภทคำร้อง": comp_type,
            "เขต": district,
            "ชุมชน": community,
            "วันที่รับเรื่อง": date_received_str,
            "วันที่เสร็จ": date_completed_str,
            "สถานะ": status
        })
        
    df = pd.DataFrame(data)
    df.to_excel(output_path, index=False, engine="openpyxl")
    print(f"Generated mock complaints data -> {output_path}")


def generate_mock_video_counts(output_path: Path):
    """Generate mock outputs/video_counts.csv containing bus_count column for pipeline tests."""
    data = [
        {
            "video_id": "Highground",
            "location_name": "ถ.ศรีจันทร์ หน้า รร. ดอนบอสโก (จุดที่ 3)",
            "direction_A_label": "tripwire_far",
            "direction_B_label": "tripwire_near",
            "direction_A_total": 1410,
            "direction_B_total": 1411,
            "bidirectional_total": 2821,
            "car_count": 1800,
            "motorcycle_count": 800,
            "truck_count": 150,
            "bus_count": 71,
            "total_unique_vehicles": 2821,
            "processed_frames": 1500,
            "video_duration_seconds": 62.5,
            "source_file": "data/videos/Highground.mp4",
            "camera_orientation": "overhead",
            "counting_method": "tripwire",
            "extrapolation_factor": 49.5,
            "extrapolation_reliable": True,
            "sample_seconds": 62.5
        },
        {
            "video_id": "Intersection",
            "location_name": "ถ.มิตรภาพ สี่แยกสามเหลี่ยม (จุดที่ 4)",
            "direction_A_label": "tripwire_left",
            "direction_B_label": "tripwire_right",
            "direction_A_total": 901,
            "direction_B_total": 902,
            "bidirectional_total": 1803,
            "car_count": 1200,
            "motorcycle_count": 500,
            "truck_count": 80,
            "bus_count": 23,
            "total_unique_vehicles": 1803,
            "processed_frames": 1500,
            "video_duration_seconds": 62.5,
            "source_file": "data/videos/Intersection.mp4",
            "camera_orientation": "sideways",
            "counting_method": "tripwire",
            "extrapolation_factor": 47.4,
            "extrapolation_reliable": True,
            "sample_seconds": 62.5
        },
        {
            "video_id": "Sideway",
            "location_name": "ถ.เหล่านาดี หน้า ม.ขอนแก่น (จุดที่ 2)",
            "direction_A_label": "tripwire_left",
            "direction_B_label": "tripwire_right",
            "direction_A_total": 106,
            "direction_B_total": 107,
            "bidirectional_total": 213,
            "car_count": 150,
            "motorcycle_count": 50,
            "truck_count": 10,
            "bus_count": 3,
            "total_unique_vehicles": 213,
            "processed_frames": 1500,
            "video_duration_seconds": 62.5,
            "source_file": "data/videos/Sideway.mp4",
            "camera_orientation": "sideways",
            "counting_method": "tripwire",
            "extrapolation_factor": 30.4,
            "extrapolation_reliable": True,
            "sample_seconds": 62.5
        }
    ]
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Generated mock video counts -> {output_path}")


def main():
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    generate_traffic_data(data_dir / "traffic_dashboard.csv")
    generate_complaints_data(data_dir / "complaints.xlsx")
    
    # Generate video_counts.csv in outputs
    outputs_dir = Path("outputs")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    generate_mock_video_counts(outputs_dir / "video_counts.csv")
    
    print("Mock data generation complete!")

if __name__ == "__main__":
    main()
