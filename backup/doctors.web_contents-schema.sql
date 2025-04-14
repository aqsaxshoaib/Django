/*!40101 SET NAMES binary*/;
/*!40014 SET FOREIGN_KEY_CHECKS=0*/;
/*!40101 SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO,ONLY_FULL_GROUP_BY,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'*/;
/*!40103 SET TIME_ZONE='+00:00' */;
CREATE TABLE `web_contents` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `main_header_cover_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardi_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardi_desc` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardii_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardii_desc` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardiii_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardiii_desc` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardiv_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardiv_desc` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardv_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardv_desc` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardvi_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_cardvi_desc` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_center_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_center_text` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_center_left_top_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_center_left_top_title_desc` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_center_left_bottom_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_center_left_bottom_title_desc` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_center_left_right_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_center_left_right_title_desc` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_footer_title` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `main_header_footer_text` text COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_520_ci;
