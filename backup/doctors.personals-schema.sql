/*!40101 SET NAMES binary*/;
/*!40014 SET FOREIGN_KEY_CHECKS=0*/;
/*!40101 SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO,ONLY_FULL_GROUP_BY,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'*/;
/*!40103 SET TIME_ZONE='+00:00' */;
CREATE TABLE `personals` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `mini_upper_subtitle` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `header_paragraph` longtext COLLATE utf8mb4_unicode_520_ci,
  `slider_status` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `about_header` longtext COLLATE utf8mb4_unicode_520_ci,
  `about_description` longtext COLLATE utf8mb4_unicode_520_ci,
  `about_status` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `about_image` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `working_hours` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `working_hours_description` longtext COLLATE utf8mb4_unicode_520_ci,
  `working_hours_status` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `our_service_header` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `our_service_description` longtext COLLATE utf8mb4_unicode_520_ci,
  `our_service_status` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `blog_header` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `blog_description` longtext COLLATE utf8mb4_unicode_520_ci,
  `blog_header_status` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `contact_header` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `contact_description` longtext COLLATE utf8mb4_unicode_520_ci,
  `contact_status` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `mobile_header` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `mobile` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `email_header` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `address_header` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `address` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `section_status` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `social_status` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_520_ci;
