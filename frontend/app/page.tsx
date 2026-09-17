import { AccessibilityToolbar } from "@/components/accessibility-toolbar";
import { HeritageLensApp } from "@/components/heritage-lens-app";
import { ArrowIcon, CameraIcon, CheckIcon, SparkIcon } from "@/components/icons";

export default function HomePage() {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Chuyển tới nội dung chính
      </a>
      <header className="site-header">
        <div className="site-shell header-inner">
          <a href="#top" className="brand" aria-label="DiSản Lens, về đầu trang">
            <span className="brand-mark" aria-hidden="true">
              <span />
            </span>
            <span>
              <strong>DiSản</strong> Lens
              <small>Nhìn để thấu hiểu</small>
            </span>
          </a>
          <nav aria-label="Điều hướng chính">
            <a href="#gioi-thieu">Giới thiệu</a>
            <a href="#cach-hoat-dong">Cách hoạt động</a>
            <a href="#nhan-dien" className="nav-cta">
              Nhận diện ngay
            </a>
          </nav>
          <AccessibilityToolbar />
        </div>
      </header>

      <main id="main-content">
        <section className="hero" id="top">
          <div className="site-shell hero-grid">
            <div className="hero-copy">
              <p className="hero-kicker">
                <SparkIcon /> Trải nghiệm lịch sử bằng công nghệ
              </p>
              <h1>
                Chụp một <em>chứng tích</em>,<br /> mở một câu chuyện
              </h1>
              <p className="hero-description">
                Đưa camera tới một hiện vật. DiSản Lens giúp em nhận diện,
                lắng nghe và tìm hiểu câu chuyện phía sau — từ dữ liệu của kho
                di sản.
              </p>
              <div className="hero-actions">
                <a href="#nhan-dien" className="button button-primary button-large">
                  <CameraIcon />
                  Bắt đầu nhận diện
                </a>
                <a href="#cach-hoat-dong" className="text-link">
                  Xem cách hoạt động
                  <ArrowIcon />
                </a>
              </div>
              <ul className="trust-list" aria-label="Cam kết của DiSản Lens">
                <li>
                  <CheckIcon /> Không lưu ảnh mặc định
                </li>
                <li>
                  <CheckIcon /> Không đoán khi điểm thấp
                </li>
                <li>
                  <CheckIcon /> Nêu rõ tình trạng nguồn
                </li>
              </ul>
            </div>
            <div className="hero-visual" aria-hidden="true">
              <div className="heritage-frame">
                <span className="frame-grid" />
                <div className="lens-core">
                  <span className="lens-glass" />
                  <span className="lens-dot" />
                </div>
                <span className="focus-corner focus-tl" />
                <span className="focus-corner focus-tr" />
                <span className="focus-corner focus-bl" />
                <span className="focus-corner focus-br" />
                <div className="visual-caption">
                  <span>01</span>
                  <p>Quan sát kỹ<br />để hiểu sâu</p>
                </div>
              </div>
              <div className="floating-note">
                <span>Di sản không im lặng</span>
                <strong>Mỗi dấu tích đều có một câu chuyện.</strong>
              </div>
            </div>
          </div>
        </section>

        <section className="intro-strip" id="gioi-thieu">
          <div className="site-shell intro-grid">
            <p className="eyebrow eyebrow-light">Một cách tiếp cận có trách nhiệm</p>
            <p>
              Công nghệ chỉ giúp tìm điểm tương đồng. Nội dung lịch sử vẫn đến
              từ dữ liệu hiện vật; khi nguồn còn thiếu, chúng tôi nói rõ điều đó.
            </p>
          </div>
        </section>

        <section className="how-section" id="cach-hoat-dong" aria-labelledby="how-title">
          <div className="site-shell">
            <div className="section-heading">
              <p className="eyebrow">Ba bước khám phá</p>
              <h2 id="how-title">Từ hình ảnh đến câu chuyện</h2>
              <p>Rõ ràng, an toàn và luôn để em kiểm tra lại kết quả.</p>
            </div>
            <ol className="how-grid">
              <li>
                <span className="how-number">01</span>
                <CameraIcon />
                <h3>Chụp rõ hiện vật</h3>
                <p>Khung căn giúp em chọn góc chụp đủ sáng và ít phản chiếu.</p>
              </li>
              <li>
                <span className="how-number">02</span>
                <SparkIcon />
                <h3>Đối chiếu có kiểm soát</h3>
                <p>Ảnh được so sánh với kho vector; kết quả thấp sẽ không bị đoán.</p>
              </li>
              <li>
                <span className="how-number">03</span>
                <ArrowIcon />
                <h3>Mở câu chuyện</h3>
                <p>Đọc nhanh, nghe thuyết minh hoặc khám phá sâu theo nhịp của em.</p>
              </li>
            </ol>
          </div>
        </section>

        <div className="site-shell app-shell">
          <HeritageLensApp />
        </div>
      </main>

      <footer className="site-footer">
        <div className="site-shell footer-grid">
          <div className="brand brand-footer">
            <span className="brand-mark" aria-hidden="true"><span /></span>
            <span><strong>DiSản</strong> Lens</span>
          </div>
          <p>
            Một dự án học tập ứng dụng AI để kết nối thế hệ trẻ với ký ức lịch sử.
          </p>
          <p className="footer-note">Ảnh truy vấn không được lưu mặc định.</p>
        </div>
      </footer>
    </>
  );
}
