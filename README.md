## 지역별 관광 트렌드 분석 플랫폼

시군구를 고르면 전년 동월대비 방문수요 변화율과 순위, 그리고 날씨 변화와의 관련 가능성을 보여주는 정적 웹페이지.
Python이 한국관광공사·기상청 데이터를 분석해 JSON으로 만들고, Vite + React 프론트엔드가 이를 읽어 보여준다.

- 요구사항: [docs/PRD.md](docs/PRD.md)
- 용어: [CONTEXT.md](CONTEXT.md)

### 실행 순서
```bash
cp .env.example .env            # DATA_GO_KR_SERVICE_KEY 에 Decoding 인증키 입력
pip install requests numpy
python analysis/fetch_visitors.py   # 방문자 일자료 수집(약 600회 호출, 중단 후 재실행하면 이어받음)
python analysis/fetch_asos.py       # ASOS 일자료 수집(약 2,300회 호출, 이어받기 지원)
python analysis/test_build.py       # 분석 함수 자체 점검
python analysis/build.py            # site/public/data/data.json 생성
cd site && npm install && npm run dev
```
배포: Docker 이미지(nginx가 빌드된 정적 파일을 제공)로 한다.
```bash
docker build -t traveltrend:latest .
docker run -d --name traveltrend -p 8080:80 traveltrend:latest   # http://localhost:8080
```
`data.json` 을 갱신하면 이미지를 다시 빌드해야 한다.
