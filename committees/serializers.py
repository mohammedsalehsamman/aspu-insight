from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Committee, CommitteeMember

User = get_user_model()

class CommitteeMemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['user_id', 'full_name', 'email', 'institution']

class CommitteeMemberSerializer(serializers.ModelSerializer):
    user = CommitteeMemberUserSerializer(read_only=True)

    class Meta:
        model = CommitteeMember
        fields = ['id', 'user', 'role', 'response', 'paper_decision', 'comments', 'assigned_at']

class CommitteeDetailsSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()
    editor_name = serializers.CharField(source='editor.full_name', read_only=True)
    paper_title = serializers.CharField(source='paper.title', read_only=True)
    paper_author_name = serializers.SerializerMethodField()
    requested_revisions = serializers.SerializerMethodField()

    class Meta:
        model = Committee
        fields = ['id', 'paper', 'paper_title', 'paper_author_name', 'editor', 'editor_name', 'status', 'blinding_type', 'members', 'requested_revisions', 'created_at']

    def get_members(self, obj):
        primary_members = obj.committee_assigned_members.filter(role='primary')
        request_user = self.context.get('request').user
        paper_author = obj.paper.author

        if request_user == paper_author and obj.blinding_type in ['single_blind', 'double_blind']:
            return [{"id": m.id, "role": "primary", "user": {"full_name": "محكم مخفي"}, "paper_decision": m.paper_decision} for m in primary_members]
            
        return CommitteeMemberSerializer(primary_members, many=True).data

    def get_paper_author_name(self, obj):
        request_user = self.context.get('request').user
        paper_author = obj.paper.author

        is_member = obj.committee_assigned_members.filter(user=request_user).exists()
        if is_member and obj.blinding_type == 'double_blind':
            return "باحث مخفي"
            
        return paper_author.full_name

    def get_requested_revisions(self, obj):
        if obj.status == 'revision':
            members_with_comments = obj.committee_assigned_members.filter(role='primary', paper_decision='modify_paper').exclude(comments__isnull=True).exclude(comments='')
            return [m.comments for m in members_with_comments]
        return []