/*!40101 SET NAMES binary*/;
/*!40014 SET FOREIGN_KEY_CHECKS=0*/;
/*!40101 SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO,ONLY_FULL_GROUP_BY,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'*/;
/*!40103 SET TIME_ZONE='+00:00' */;
CREATE TABLE `social_media_links` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `facebook` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `whatsapp` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `youtube` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `instagram` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `tiktok` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `telegram` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `snapchat` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `twitter` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `pinterest` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `social_media_links_user_id_foreign` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_520_ci;
