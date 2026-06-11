from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    message = ' this action is only allowed for administrators.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == 'admin'
        )


class IsEditor(BasePermission):
    message = 'this action is only allowed for editors.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ['editor', 'admin']
        )


class IsAssistantEditor(BasePermission):
    message = 'this action is only allowed for assistant editors.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ['reviewer_assistant', 'admin']
        )


class IsReviewer(BasePermission):
    message = 'this action is only allowed for reviewers.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ['reviewer', 'reviewer_assistant', 'admin']
        )


class IsAuthor(BasePermission):
    message = 'this action is only allowed for authors.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ['author', 'admin']
        )


class IsReader(BasePermission):
    message = 'this action is only allowed for readers.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class CanManageUsers(BasePermission):
    message = 'this action is only allowed for administrators.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == 'admin'
        )


class IsEmailVerified(BasePermission):
    message = 'this action is only allowed for verified email users.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.email_verified
        )


class IsOwnerOrAdmin(BasePermission):
    message = 'this action is only allowed for the owner or administrators.'

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user and
            request.user.is_authenticated and
            (obj == request.user or request.user.role == 'admin')
        )
