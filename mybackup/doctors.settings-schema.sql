/*!40101 SET NAMES binary*/;
/*!40014 SET FOREIGN_KEY_CHECKS=0*/;
/*!40101 SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO,ONLY_FULL_GROUP_BY,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'*/;
/*!40103 SET TIME_ZONE='+00:00' */;
CREATE TABLE `settings` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `user_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `footer` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `google` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `author` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `keywords` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `tags` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `website_logo` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `fav_icon` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_520_ci,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_520_ci;
