"use client";

import { useState } from "react";
import { ArrowIcon, SparkIcon } from "@/components/icons";
import { toThumbnailUrl } from "@/lib/api";

interface FeaturedDiscovery {
  itemId: string;
  imageId: string;
  title: string;
  focus: string;
  description: string;
  alt: string;
}

const FEATURED_DISCOVERIES: FeaturedDiscovery[] = [
  {
    itemId: "tuong-ba-me-bang-manh-bom",
    imageId: "tuong-ba-me-bang-manh-bom_01",
    title: "Tượng Bà mẹ bằng mảnh bom",
    focus: "Nghệ thuật từ chứng tích chiến tranh",
    description:
      "Tìm hiểu cách những mảnh bom được chuyển hóa thành hình tượng người mẹ, đặt mất mát bên cạnh khát vọng gìn giữ sự sống.",
    alt: "Tượng Bà mẹ được tạo hình từ những mảnh bom trong không gian trưng bày",
  },
  {
    itemId: "truc-thang-uh1",
    imageId: "truc-thang-uh1_01",
    title: "Trực thăng UH-1",
    focus: "Phương tiện đường không",
    description:
      "Quan sát cấu tạo bên ngoài của UH-1 và tìm hiểu vai trò cơ động lực lượng của trực thăng trong chiến tranh Việt Nam.",
    alt: "Trực thăng quân sự UH-1 được trưng bày ngoài trời tại bảo tàng",
  },
  {
    itemId: "ban-do-vung-bi-rai-chat-doc-hoa-hoc",
    imageId: "ban-do-vung-bi-rai-chat-doc-hoa-hoc_01",
    title: "Bản đồ vùng bị rải chất độc hóa học",
    focus: "Dấu vết chiến tranh hóa học",
    description:
      "Đọc bản đồ để hình dung phạm vi địa lý của hoạt động rải chất độc hóa học và những khu vực chịu hậu quả lâu dài.",
    alt: "Bản đồ trưng bày các vùng bị rải chất độc hóa học trong chiến tranh Đông Dương lần thứ hai",
  },
  {
    itemId: "sap-dat-nghe-thuat-hoa-binh",
    imageId: "sap-dat-nghe-thuat-hoa-binh_01",
    title: "Sắp đặt nghệ thuật hòa bình",
    focus: "Đoàn kết quốc tế và hòa bình",
    description:
      "Khám phá cách hình ảnh, hiện vật và không gian nghệ thuật kết nối ký ức chiến tranh với các phong trào ủng hộ hòa bình.",
    alt: "Không gian sắp đặt nghệ thuật với thông điệp hòa bình và đoàn kết quốc tế",
  },
];

interface FeaturedDiscoveriesProps {
  busy?: boolean;
  onSelect: (itemId: string) => void;
}

export function FeaturedDiscoveries({
  busy = false,
  onSelect,
}: FeaturedDiscoveriesProps) {
  return (
    <section
      className="featured-discoveries"
      aria-labelledby="featured-discoveries-title"
    >
      <div className="featured-heading">
        <div>
          <p className="eyebrow">
            <SparkIcon /> Gợi ý xem thêm
          </p>
          <h2 id="featured-discoveries-title">Bốn lát cắt đáng khám phá</h2>
        </div>
        <p>
          Chọn một hình ảnh để mở câu chuyện, bối cảnh lịch sử, mindmap và thử
          thách liên quan — không cần chụp ảnh trước.
        </p>
      </div>

      <ul className="featured-grid">
        {FEATURED_DISCOVERIES.map((item) => (
          <li key={item.itemId}>
            <button
              type="button"
              className="featured-card"
              onClick={() => onSelect(item.itemId)}
              disabled={busy}
              aria-label={`Khám phá ${item.title}`}
            >
              <FeaturedImage item={item} />
              <span className="featured-card-copy">
                <span className="featured-focus">{item.focus}</span>
                <strong>{item.title}</strong>
                <span>{item.description}</span>
                <span className="featured-card-link">
                  Xem câu chuyện <ArrowIcon />
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>

      <div className="featured-more">
        <p>
          Muốn xem thêm ảnh theo từng bộ sưu tập? Hãy tiếp tục tại kho ảnh tư
          liệu do Bảo tàng công bố.
        </p>
        <a
          className="button button-secondary"
          href="https://baotangchungtichchientranh.vn/vi/kham-pha/anh-tu-lieu"
          target="_blank"
          rel="noopener noreferrer"
        >
          Xem kho ảnh tư liệu chính thức <ArrowIcon />
        </a>
      </div>
    </section>
  );
}

function FeaturedImage({ item }: { item: FeaturedDiscovery }) {
  const [failed, setFailed] = useState(false);
  const imageUrl = toThumbnailUrl(
    `/api/v1/artifacts/${encodeURIComponent(item.itemId)}/images/${encodeURIComponent(item.imageId)}`,
    640,
  );

  return (
    <span className="featured-image">
      {!failed && imageUrl ? (
        // Backend URLs are runtime-configured, so a native image is used here.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imageUrl}
          alt={item.alt}
          width={640}
          height={480}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="featured-image-fallback" aria-hidden="true">
          DiSản Lens
        </span>
      )}
    </span>
  );
}
