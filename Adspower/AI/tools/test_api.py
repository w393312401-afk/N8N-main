import requests
import json
import os

BASE_URL = "http://127.0.0.1:8000"

def test_endpoint(path, payload, method="POST"):
    url = f"{BASE_URL}{path}"
    print(f"\nTesting {method} {path}")
    print(f"Payload: {json.dumps(payload)}")
    try:
        if method == "POST":
            response = requests.post(url, json=payload)
        else:
            response = requests.get(url)
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test health check
    test_endpoint("/", {}, method="GET")

    # Test /generate_video with incomplete payload
    test_endpoint("/generate_video", {
        "user_id": "test_user"
    })

    # Test /analyze/json (JSON)
    test_endpoint("/analyze/json", {
        "prompt": "describe this image",
        "file_paths": ["test.png"]
    })

    # Test /analyze (Form Data)
    print(f"\nTesting POST /analyze (Form Data)")
    try:
        url = f"{BASE_URL}/analyze"
        payload = {"prompt": "describe this image", "file_paths": "test1.png,test2.png"}
        print(f"Payload: {payload}")
        response = requests.post(url, data=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

    # Test /merge_videos
    # 创建两个假的视频文件用于测试 (如果不存在的话)
    dummy_video_1 = "/Users/fly/Desktop/N8N-main/output/test_v1.mp4"
    dummy_video_2 = "/Users/fly/Desktop/N8N-main/output/test_v2.mp4"
    
    # 写入空文件只是为了路径存在性检查 (ffmpeg 会报错，但我们可以看 API 是否调用成功)
    # 或者如果想让 ffmpeg 真正跑通，需要真实的 mp4。
    # 这里我们只测试 API 逻辑是否跑通 (收到 invalid data error 也是一种 success response from API perspective)
    
    if not os.path.exists("/Users/fly/Desktop/N8N-main/output"):
        os.makedirs("/Users/fly/Desktop/N8N-main/output")
        
    with open(dummy_video_1, "w") as f: f.write("dummy content")
    with open(dummy_video_2, "w") as f: f.write("dummy content")

    test_endpoint("/merge_videos", {
        "video_paths": [dummy_video_1, dummy_video_2],
        "output_filename": "test_merged_result.mp4"
    })
